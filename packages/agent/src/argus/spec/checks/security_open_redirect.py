from .common import define_check

CHECK = define_check(
    id="security-open-redirect",
    title="Untrusted redirect target",
    category="security",
    family="form",
    action="fill",
    value="https://example.invalid/",
    expected="Untrusted redirect targets cannot send users off-site.",
)

