from .common import define_check

CHECK = define_check(
    id="list-long-item-name",
    title="Long item names",
    category="lists",
    family="list",
    action="assert_no_text_overflow",
    value=None,
    expected="Long labels remain readable and do not overlap adjacent controls.",
)

