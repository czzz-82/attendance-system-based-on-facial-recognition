"""人脸超分模块：基于 GFPGAN，用于修复模糊或远距离人脸"""
import cv2
import numpy as np

class FaceEnhancer:
    def __init__(self, model_version='1.4', upscale=2):
        print("正在加载 GFPGAN 人脸超分模型...")
        try:
            from gfpgan import GFPGANer
            self.restorer = GFPGANer(
                model_path=f'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv{model_version}.pth',
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