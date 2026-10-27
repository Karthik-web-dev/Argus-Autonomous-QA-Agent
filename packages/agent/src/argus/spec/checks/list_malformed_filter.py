from .common import define_check

CHECK = define_check(
    id="list-malformed-filter",
    title="Malformed filter",
    category="lists",
    family="form",
    action="fill",
    value="%zz[",
    expected="Malformed filter input is handled without a client or server error.",
    flow="malformed_filter",
)

