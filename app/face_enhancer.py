"""人脸超分模块：基于 GFPGAN，用于修复模糊或远距离人脸"""
import cv2
import numpy as np
import config


def _install_torchvision_compat():
    """???? torchvision?basicsr/gfpgan ???? functional_tensor?"""
    try:
        import sys
        import types
        import torchvision.transforms.functional as tv_functional
        module_name = "torchvision.transforms.functional_tensor"
        if module_name not in sys.modules:
            shim = types.ModuleType(module_name)
            shim.rgb_to_grayscale = tv_functional.rgb_to_grayscale
            sys.modules[module_name] = shim
    except Exception:
        pass

class FaceEnhancer:
    def __init__(self, model_version='1.4', upscale=2):
        print("正在加载 GFPGAN 人脸超分模型...")
        try:
            _install_torchvision_compat()
            from gfpgan import GFPGANer
            import os
            local_model = os.path.join(config.BASE_DIR, "models", f"GFPGANv{model_version}.pth")
            model_path = local_model if os.path.exists(local_model) else f'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv{model_version}.pth'
            self.restorer = GFPGANer(
                model_path=model_path,
                upscale=upscale,
                arch='clean',
                channel_multiplier=2,
                bg_upsampler=None 
            )
            print("GFPGAN 模型加载完成！")
            self.loaded = True
        except ImportError:
            print("警告: 未安装 gfpgan，超分功能将被禁用。")
            self.loaded = False
        except Exception as e:
            print(f"GFPGAN 模型加载失败: {e}")
            self.loaded = False

    def enhance(self, face_img_bgr: np.ndarray) -> np.ndarray:
        if not self.loaded:
            return face_img_bgr
        try:
            # 执行超分
            cropped_faces, restored_faces, restored_img = self.restorer.enhance(
                face_img_bgr,
                has_aligned=False,
                only_center_face=False,
                paste_back=True
            )
            return restored_img if restored_img is not None else face_img_bgr
        except Exception as e:
            print(f"超分处理异常: {e}")
            return face_img_bgr