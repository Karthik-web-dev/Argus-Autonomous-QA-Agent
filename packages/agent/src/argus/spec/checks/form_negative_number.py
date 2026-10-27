from .common import define_check

CHECK = define_check(
    id="form-negative-number",
    title="Negative number in a non-negative field",
    category="forms",
    family="numeric",
    action="fill",
    value="-42",
    expected="A negative value is rejected when the field requires a non-negative number.",
    flow="invalid",
)
