"""FIDC amortization app package."""

from fidc.excel import ExcelInputs, load_excel_inputs
from fidc.model import ModelInputs, ModelOutputs, run_model

__all__ = ["ExcelInputs", "load_excel_inputs", "ModelInputs", "ModelOutputs", "run_model"]
