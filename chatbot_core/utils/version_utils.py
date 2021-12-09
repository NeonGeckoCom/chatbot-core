import os
from typing import Type

version = os.environ.get('CHATBOT_VERSION', 'v1').lower()


def get_class(version_class_mapping: dict) -> Type:
    """
        Get class matching current CHATBOT_VERSION

        :param version_class_mapping: mapping between version and class instance

        :returns Class instance matching current version if any
    """
    return version_class_mapping.get(version, None)
