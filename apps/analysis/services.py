import logging

from .client import predict as analysis_predict

logger = logging.getLogger(__name__)


def classify_leaf(image_file) -> dict:
    return analysis_predict(image_file)
