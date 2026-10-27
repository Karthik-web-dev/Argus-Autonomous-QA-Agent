from .common import define_check

CHECK = define_check(
    id="form-negative-zero",
    title="Negative and zero values",
    category="forms",
    family="numeric",
    action="fill",
    value="-0",
    expected="Numeric values at zero and below-zero boundaries follow the documented rule.",
    flow="zero_equivalence",
)

