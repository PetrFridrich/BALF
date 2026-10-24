from pathlib import Path
import torch
import os
from skimage import io
from model.BALF_Model import BALFModel
import common.helper_plot as helper_plot
import common.helper as helper
import config


class ModelInference:

    def __init__(self, path_to_model, path_to_images, path_to_annotations=None):
        
        self.model = self.load_model(path_to_model)

        self.path_to_images = path_to_images
        self.path_to_annotations = path_to_annotations

        self.model.eval()


    def perform_inference(self, output_path):

        image_names = os.listdir(self.path_to_images)

        for i, img_name in enumerate(image_names):
            path_to_img = self.path_to_images / Path(img_name)
            img = io.imread(path_to_img)
            img = img / 255.0
            img_per = torch.tensor(img, dtype=torch.float32).permute(2, 0, 1)  # permute dimensions: (H, W, C) -> (C, H, W)

            with torch.no_grad():
                pred = self.model(img_per.unsqueeze(0))

                helper_plot.visualize_prediction(img, pred, f'{output_path / Path(config.subdirs[0]) / path_to_img.stem}.png')
                helper.create_xml_annotation(pred, path_to_img, output_path / Path(config.subdirs[1]), img.shape)

        return None
    

    def load_model(self, path_to_model):
        return BALFModel.load_from_checkpoint(path_to_model)
