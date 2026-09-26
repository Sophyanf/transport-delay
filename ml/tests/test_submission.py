import pandas as pd
import pytest
from transport_ml.validation import validate_submission


# Создаёт корректный шаблон конкурсного файла.
def create_submission_template() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["sample-1", "sample-2"],
            "prediction": [0.0, 0.0],
        }
    )


# Проверяет корректный конкурсный файл.
def test_validate_submission_accepts_valid_frame() -> None:
    template = create_submission_template()
    submission = template.copy()
    submission["prediction"] = [10.0, -5.0]
    validate_submission(submission, template)


# Проверяет запрет изменённого порядка sample_id.
def test_validate_submission_rejects_wrong_order() -> None:
    template = create_submission_template()
    submission = template.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError):
        validate_submission(submission, template)
