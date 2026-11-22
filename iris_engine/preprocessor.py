import cv2
import numpy as np

class LightingCompensator:

    def __init__(self, clip_limit: float=2.0, tile_grid_size: tuple=(8, 8)):
        self.clip_limit = clip_limit
        self.tile_grid_size = tile_grid_size
        self._clahe = cv2.createCLAHE(clipLimit=self.clip_limit, tileGridSize=self.tile_grid_size)

    def process(self, frame_bgr: np.ndarray) -> np.ndarray:
        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        ycrcb[:, :, 0] = self._clahe.apply(ycrcb[:, :, 0])
        rgb_normalized = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)
        return rgb_normalized

    def update_params(self, clip_limit: float=2.0, tile_grid_size: tuple=(8, 8)) -> None:
        self.clip_limit = clip_limit
        self.tile_grid_size = tile_grid_size
        self._clahe = cv2.createCLAHE(clipLimit=self.clip_limit, tileGridSize=self.tile_grid_size)
