# common/utils.py
def enum_to_choices(enum_cls):
    return [
        {
            "code": choice.value,
            "label": choice.label
        }
        for choice in enum_cls
    ]
