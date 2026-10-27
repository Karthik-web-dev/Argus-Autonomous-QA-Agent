from .common import define_check

CHECK = define_check(
    id="form-decimal-integer",
    title="Decimal in an integer field",
    category="forms",
    family="numeric",
    action="fill",
    value="1.5",
    expected="A decimal value in an integer-only field is rejected or normalized by an explicit rule.",
    flow="invalid",
)
