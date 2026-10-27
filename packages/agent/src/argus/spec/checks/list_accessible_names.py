from .common import define_check

CHECK = define_check(
    id="list-accessible-names",
    title="Accessible list action names",
    category="lists",
    family="list",
    action="assert_named_control",
    value=None,
    expected="Interactive list controls expose unique accessible names.",
)

