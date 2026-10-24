import os
from pathlib import Path
from sklearn.model_selection import train_test_split
from pytorch_lightning import LightningDataModule
from torch.utils.data import DataLoader
from model.BALF_Dataset import CellDataset


RANDOM_STATE_SEED = 42


class CellDataModule(LightningDataModule):

    def __init__(self, 
                 path_images, 
                 path_annotations, 
                 batch_size=2,
                 num_of_workers=0,
                 train_ratio=0.6):

        super().__init__()

        # Images
        self.image_paths = self.get_paths(path_images)

        # Annotations
        self.annotation_paths = self.get_paths(path_annotations)

        # Setting
        self.batch_size = batch_size
        self.num_of_workers = num_of_workers
        self.train_ratio = train_ratio

        # Dataset parts
        self.train = None
        self.val = None
        self.test = None

    
    def get_paths(self, path):

        file_names = os.listdir(path)
        paths = [Path(os.path.join(path, name)) for name in file_names]

        return paths


    def setup(self, stage=None):

        # Split data to Train and Rest
        x_train, x_rest, y_train, y_rest = train_test_split(self.image_paths, 
                                                            self.annotation_paths, 
                                                            train_size=self.train_ratio, 
                                                            random_state=RANDOM_STATE_SEED)

        # Split rest to Validation and Test
        x_val, x_test, y_val, y_test = train_test_split(x_rest, y_rest, test_size=0.5, random_state=RANDOM_STATE_SEED)

        # Creating datasets
        self.train = CellDataset(x_train, y_train)
        self.val = CellDataset(x_val, y_val)
        self.test = CellDataset(x_test, y_test)


    def train_dataloader(self):
        if not self.train:
            raise Exception("need to call setup() first")
        return DataLoader(self.train, batch_size=self.batch_size, num_workers=self.num_of_workers, shuffle=True, collate_fn=self.collate_fn)


    def val_dataloader(self):
        if not self.val:
            raise Exception("need to call setup() first")
        return DataLoader(self.val, batch_size=self.batch_size, num_workers=self.num_of_workers, shuffle=False, collate_fn=self.collate_fn)


    def test_dataloader(self):
        if not self.test:
            raise Exception("need to call setup() first")
        return DataLoader(self.test, batch_size=self.batch_size, num_workers=self.num_of_workers, shuffle=False, collate_fn=self.collate_fn)


    def collate_fn(self, batch):
        return tuple(zip(*batch))
    
