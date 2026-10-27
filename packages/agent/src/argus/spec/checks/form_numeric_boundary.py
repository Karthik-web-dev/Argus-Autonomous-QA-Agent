from .common import define_check

CHECK = define_check(
    id="form-numeric-boundary",
    title="Numeric boundary values",
    category="forms",
    family="numeric",
    action="fill",
    value="999999999999999999999999",
    expected="Numeric bounds are enforced without overflow.",
    flow="numeric_boundary",
)

