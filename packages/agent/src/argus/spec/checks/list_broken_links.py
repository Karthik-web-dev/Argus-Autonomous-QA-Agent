from .common import define_check

CHECK = define_check(
    id="list-broken-links",
    title="Broken links",
    category="lists",
    family="any",
    action="assert_internal_links",
    value=None,
    expected="Visible list links resolve to the intended in-app destinations.",
)

