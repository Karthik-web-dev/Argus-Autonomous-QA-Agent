from .common import define_check

CHECK = define_check(
    id="form-zero-number",
    title="Zero numeric value",
    category="forms",
    family="numeric",
    action="fill",
    value="0",
    expected="Zero is handled correctly at the field's lower boundary.",
    flow="numeric_value",
)
