import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")

from catboost import CatBoostRegressor, Pool
from sklearn.metrics import mean_absolute_error

CAT_FEATURES = ["tr_id", "target_stop_id"]

print("Загрузка данных...")
labels = pd.read_csv("data/raw/labels/labels_train.csv")
test_labels = pd.read_csv("data/raw/labels/labels_test.csv")
traffic = pd.read_csv("data/raw/train/traffic.csv", parse_dates=["event_time"])
val_points = pd.read_csv("data/raw/validate/points.csv")
val_traffic = pd.read_csv("data/raw/validate/traffic.csv", parse_dates=["event_time"])

for df in (labels, test_labels, val_points):
    df["T"] = pd.to_datetime(df["T"])
    df["target_time_begin"] = pd.to_datetime(df["target_time_begin"])

print("Построение признаков...")

def build_features(points, traffic_full):
    traffic_full = traffic_full[traffic_full["speed"].notna()].copy()
    feats = list()
    for tr_id, grp in points.groupby("tr_id"):
        t = traffic_full[traffic_full.tr_id == tr_id]
        if t.empty:
            continue
        t = t.sort_values("event_time")
        grp = grp.sort_values("T")
        merged = pd.merge_asof(
            grp, t[["event_time", "speed", "lat", "lon", "heading"]],
            left_on="T", right_on="event_time", direction="backward",
        )
        feats.append(merged)

    if not feats:
        return pd.DataFrame()

    df = pd.concat(feats, ignore_index=True)

    roll_feats = list()
    for tr_id, grp in points.groupby("tr_id"):
        t = traffic_full[traffic_full.tr_id == tr_id].sort_values("event_time")
        if t.empty:
            continue
        s = t.set_index("event_time")
        for _, row in grp.iterrows():
            window = s.loc[row["T"] - pd.Timedelta(minutes=10): row["T"]]
            if not window.empty:
                roll_feats.append({
                    "sample_id": row["sample_id"],
                    "speed_mean_10m": window["speed"].mean(),
                    "speed_min_10m": window["speed"].min(),
                    "speed_max_10m": window["speed"].max(),
                    "speed_std_10m": window["speed"].std(),
                    "idle_frac_10m": (window["speed"] < 5).mean(),
                    "n_points_10m": len(window),
                })

    roll_df = pd.DataFrame(roll_feats)
    if not roll_df.empty:
        df = df.merge(roll_df, on="sample_id", how="left")

    return df


def finalize(frame, pts):
    frame["time_to_target"] = (
        pts.set_index("sample_id")["target_time_begin"].loc[frame["sample_id"]].values
        - frame["T"].values
    ) / np.timedelta64(1, "s")
    frame["cur_dev_s"] = pts.set_index("sample_id")["cur_dev_s"].loc[frame["sample_id"]].values
    frame["hour"] = frame["T"].dt.hour
    frame["dayofweek"] = frame["T"].dt.dayofweek
    for col in CAT_FEATURES:
        if col not in frame.columns:
            frame[col] = "__missing__"
        frame[col] = frame[col].fillna("__missing__").astype(str)
    return frame


train_feats = finalize(build_features(labels, traffic), labels)
test_feats = finalize(build_features(test_labels, traffic), test_labels)
val_feats = finalize(build_features(val_points, val_traffic), val_points)

FEATURES = [
    "cur_dev_s",
    "speed_mean_10m", "speed_min_10m", "speed_max_10m", "speed_std_10m",
    "idle_frac_10m", "n_points_10m",
    "time_to_target", "hour", "dayofweek",
] + CAT_FEATURES

train_feats = train_feats.dropna(subset=["cur_dev_s"])
test_feats = test_feats.dropna(subset=["cur_dev_s"])

train_feats["residual"] = train_feats["target_delay_s"] - train_feats["cur_dev_s"]
test_feats["residual"] = test_feats["target_delay_s"] - test_feats["cur_dev_s"]

def make_model(seed, iterations, verbose):
    return CatBoostRegressor(
        loss_function="MAE", depth=6, learning_rate=0.03, l2_leaf_reg=10,
        iterations=iterations, random_seed=seed,
        od_type="Iter", od_wait=300, verbose=verbose, thread_count=-1,
    )

print("Проверка на test...")
eval_model = make_model(42, 5000, 200)
eval_model.fit(
    train_feats[FEATURES], train_feats["residual"],
    cat_features=CAT_FEATURES,
    eval_set=(test_feats[FEATURES], test_feats["residual"]),
    use_best_model=True,
)

pred_resid = eval_model.predict(test_feats[FEATURES])
current = test_feats["cur_dev_s"].to_numpy(float)
target = test_feats["target_delay_s"].to_numpy(float)

print(f"baseline cur_dev_s MAE: {mean_absolute_error(target, current):.4f}")
print(f"model MAE (alpha=1): {mean_absolute_error(target, current + pred_resid):.4f}")

best_alpha, best_mae = 1.0, np.inf
for alpha in np.arange(0.0, 1.51, 0.05):
    mae = mean_absolute_error(target, current + alpha * pred_resid)
    if mae < best_mae:
        best_alpha, best_mae = alpha, mae
print(f"best alpha={best_alpha:.2f}, MAE={best_mae:.4f} (подобрано на test, оптимистично)")

best_iter = eval_model.get_best_iteration()
if best_iter is None or best_iter < 0:
    best_iter = eval_model.get_params()["iterations"] - 1
final_iterations = max(1, int((best_iter + 1) * 1.15))

print(f"Финальное обучение на train+test, iterations={final_iterations}...")
final_frame = pd.concat([train_feats, test_feats], ignore_index=True)
SEEDS = [42, 7, 2026]
models = []
for seed in SEEDS:
    m = make_model(seed, final_iterations, 0)
    m.fit(final_frame[FEATURES], final_frame["residual"], cat_features=CAT_FEATURES)
    models.append(m)

print("Формирование сабмита для validate...")
val_ok = val_feats.dropna(subset=["cur_dev_s"]).copy()
resid_pred = np.mean([m.predict(val_ok[FEATURES]) for m in models], axis=0)
val_ok["pred"] = val_ok["cur_dev_s"].to_numpy(float) + best_alpha * resid_pred

missing = val_points[~val_points["sample_id"].isin(val_ok["sample_id"])]
submission = pd.concat([
    val_ok[["sample_id", "pred"]].rename(columns={"pred": "prediction"}),
    missing[["sample_id", "cur_dev_s"]].rename(columns={"cur_dev_s": "prediction"}),
], ignore_index=True)

submission.to_csv("submission.csv", index=False, sep=";")
print(f"Готово! submission.csv создан. Строк: {len(submission)}")
import os

os.makedirs("ml/models/catboost_residual_v1/artifacts", exist_ok=True)
eval_model.save_model(
    "ml/models/catboost_residual_v1/artifacts/model.cbm",
    format="cbm",
)
print("Модель сохранена в ml/models/catboost_residual_v1/artifacts/model.cbm")
