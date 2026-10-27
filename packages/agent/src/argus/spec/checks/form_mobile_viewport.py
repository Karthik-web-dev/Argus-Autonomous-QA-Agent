from .common import define_check

CHECK = define_check(
    id="form-mobile-viewport",
    title="Mobile viewport form layout",
    category="forms",
    family="form",
    action="assert",
    value="form",
    expected="The form remains usable at a narrow viewport without clipped controls.",
    flow="mobile",
)

