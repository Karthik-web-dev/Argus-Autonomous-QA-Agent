from .common import define_check

CHECK = define_check(
    id="form-double-submit",
    title="Double submission",
    category="forms",
    family="submit",
    action="assert_double_submit",
    value=None,
    expected="A repeated submit action creates at most one mutation.",
    flow="double_submit",
)

