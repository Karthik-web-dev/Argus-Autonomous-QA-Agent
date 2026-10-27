from .common import define_check

CHECK = define_check(
    id="security-idor",
    title="Cross-account object access",
    category="security",
    family="any",
    action="assert_idor_isolation",
    value=None,
    expected="A user cannot read or change another account's private object.",
)

