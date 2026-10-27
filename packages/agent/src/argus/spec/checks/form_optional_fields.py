from .common import define_check

CHECK = define_check(
    id="form-optional-fields",
    title="Omitted optional fields",
    category="forms",
    family="form",
    action="fill",
    value="",
    expected="Optional fields may be omitted without blocking a valid submission.",
)

