from .common import define_check

CHECK = define_check(
    id="security-logged-out-protected",
    title="Logged-out protected route",
    category="security",
    family="any",
    action="goto",
    value="/account",
    expected="Protected content is not exposed to a logged-out visitor.",
    flow="protected_route",
)

