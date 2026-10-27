from .common import define_check

CHECK = define_check(
    id="form-invalid-email",
    title="Invalid email address",
    category="forms",
    family="email",
    action="fill",
    value="not-an-email",
    expected="Invalid email input is rejected with an accessible validation message.",
    flow="invalid",
)

