from skimage import io
import albumentations as A
from albumentations.pytorch import ToTensorV2
import torch
from torch.utils.data import Dataset
import xml.etree.ElementTree as ET
import common.mapping as m


class CellDataset(Dataset):

    def __init__(self, images_path, annotations_path, transforms=None):

        self.images_path = images_path
        self.annotations = annotations_path
        self.transforms = transforms if transforms is not None else self.default_transforms()
        
        self.n_images = len(images_path)


    def __len__(self):
        return self.n_images


    def __getitem__(self, index):

        # Image
        image = io.imread(self.images_path[index])

        # Annotation
        bboxes = self.load_annotation(index)

        # Apply augmentations
        if self.transforms:
            augmented = self.transforms(image=image, bboxes=bboxes)
            image = augmented['image']
            boxes = [bbox[:4] for bbox in augmented['bboxes']]
            labels = [int(bbox[4]) for bbox in augmented['bboxes']]

        target = dict()
        target['boxes'] = torch.tensor(boxes, dtype=torch.int64)
        target['labels'] = torch.tensor(labels)

        return image, target


    def load_annotation(self, index):
        tree = ET.parse(self.annotations[index])
        root = tree.getroot()

        cell_bbs = []
        cell_types = []

        for obj in root.findall('object'):
            cell_type = m.map_name_to_lbl.get(obj.find('name').text, 1)
            cell_types.append(cell_type)

            bb = obj.find('bndbox')
            cell_bb = [
                int(bb.find('xmin').text),
                int(bb.find('ymin').text),
                int(bb.find('xmax').text),
                int(bb.find('ymax').text)
            ]
            cell_bbs.append(cell_bb)

            bboxes = [box + [label] for box, label in zip(cell_bbs, cell_types)]

        return bboxes


    def default_transforms(self):

        return A.Compose([
            # Flipping
            A.VerticalFlip(),
            A.HorizontalFlip(),

            # Image modification
            A.RandomBrightnessContrast(brightness_limit=0.1, contrast_limit=0.1, p=0.5),
            A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=15, val_shift_limit=10, p=0.5),

            # Convert to float
            A.ToFloat(max_value=255),

            # Permute shape: (H, W, C) -> (C, H, W)
            ToTensorV2()

        ], bbox_params=A.BboxParams(format='pascal_voc'))


