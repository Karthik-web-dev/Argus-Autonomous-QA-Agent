from .common import define_check

CHECK = define_check(
    id="list-console-errors",
    title="List console errors",
    category="lists",
    family="any",
    action="assert_no_console_errors",
    value=None,
    expected="List interactions produce no uncaught browser console errors.",
)

