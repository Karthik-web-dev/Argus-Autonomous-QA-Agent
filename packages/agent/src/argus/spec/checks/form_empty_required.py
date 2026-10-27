from .common import define_check

CHECK = define_check(
    id="form-empty-required",
    title="Empty required field",
    category="forms",
    family="required",
    action="fill",
    value="",
    expected="Required fields reject empty input with a clear validation message.",
    flow="invalid",
)

