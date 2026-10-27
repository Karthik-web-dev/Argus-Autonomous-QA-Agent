from .common import define_check

CHECK = define_check(
    id="form-validation-order",
    title="Multiple field validation",
    category="forms",
    family="form",
    action="fill",
    value="invalid value",
    expected="Validation identifies the relevant field and does not hide other errors.",
)

