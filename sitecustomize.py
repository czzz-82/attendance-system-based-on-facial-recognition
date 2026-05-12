"""Local dependency compatibility shims for the attendance demo project."""
import sys
import types

# basicsr/gfpgan 1.4.x imports torchvision.transforms.functional_tensor,
# which was removed in newer torchvision. Re-export the used function.
try:
    import torchvision.transforms.functional as _tv_functional
    _mod = types.ModuleType("torchvision.transforms.functional_tensor")
    _mod.rgb_to_grayscale = _tv_functional.rgb_to_grayscale
    sys.modules.setdefault("torchvision.transforms.functional_tensor", _mod)
except Exception:
    pass
