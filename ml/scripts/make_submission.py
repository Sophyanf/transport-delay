import argparse
from pathlib import Path

import pandas as pd
from transport_ml.io import (
    read_csv_file,
    read_parquet_file,
    write_submission_csv,
)
from transport_ml.validation import (
    validate_submission,
    validate_unique_identifier,
)


# Читает аргументы формирования submission.
def parse_make_submission_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


# Объединяет шаблон с прогнозами в исходном порядке.
def build_submission(
    template: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    validate_unique_identifier(template, "sample_id", "template")
    validate_unique_identifier(predictions, "sample_id", "predictions")
    base = template[["sample_id"]].copy()
    base["sample_id"] = base["sample_id"].astype(str)
    prepared_predictions = predictions[["sample_id", "prediction"]].copy()
    prepared_predictions["sample_id"] = prepared_predictions["sample_id"].astype(str)
    return base.merge(
        prepared_predictions,
        on="sample_id",
        how="left",
        sort=False,
        validate="one_to_one",
    )


# Сохраняет и повторно проверяет submission.
def execute_make_submission(
    template: pd.DataFrame,
    predictions: pd.DataFrame,
    output_path: Path,
) -> None:
    submission = build_submission(template, predictions)
    validate_submission(submission, template)
    write_submission_csv(submission, output_path)
    restored = read_csv_file(output_path, separator=";")
    validate_submission(restored, template)


# Запускает формирование конкурсного файла.
def main() -> None:
    arguments = parse_make_submission_arguments()
    template = read_csv_file(arguments.template, separator=";")
    predictions = read_parquet_file(arguments.predictions)
    execute_make_submission(
        template,
        predictions,
        arguments.output,
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
