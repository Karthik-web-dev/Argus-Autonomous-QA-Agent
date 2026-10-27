from .common import define_check

CHECK = define_check(
    id="security-session-expiry",
    title="Expired session",
    category="security",
    family="list",
    action="click",
    value=None,
    expected="Expired sessions are redirected safely and private data is cleared.",
)

