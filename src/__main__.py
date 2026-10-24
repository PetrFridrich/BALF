import pytorch_lightning as pl
from model.BALF_Model import BALFModel
from model.BALF_ModelInference import ModelInference
from model.BALF_DataModule import CellDataModule
from pytorch_lightning.loggers import TensorBoardLogger
import config
import re
import common.helper as helper


def train_and_test_main():

    tensor_board_logger = TensorBoardLogger(config.log_dir, name=config.name)
    trainer = pl.Trainer(max_epochs=config.max_epochs, logger=tensor_board_logger)

    data_module = CellDataModule(
        path_images=config.path_images,
        path_annotations=config.path_annotations,
        batch_size=config.batch_size,
        num_of_workers=config.num_of_workers,
        train_ratio=config.train_ratio
    )

    data_module.setup()

    # Initialize the model
    model = BALFModel(num_classes=config.num_classes, 
                      learning_rate=config.learning_rate
    )
    
    # Train the model
    trainer.fit(model, datamodule=data_module)
    
    # Test the model after training
    trainer.test(model, datamodule=data_module)

    return None


def test_main():

    # Extracts the version number from path
    version = int(re.search(r"version_(\d+)", str(config.path_to_model)).group(1))
    
    # Initialize logger using the existing directory
    tensor_board_logger = TensorBoardLogger(config.log_dir, name=config.name, version=version)

    # Initialize the trainer
    trainer = pl.Trainer(logger=tensor_board_logger)

    # Initialize the data module
    data_module = CellDataModule(
        path_images=config.path_images,
        path_annotations=config.path_annotations,
        batch_size=config.batch_size,
        num_of_workers=config.num_of_workers,
        train_ratio=config.train_ratio
    )

    # Load the model from checkpoint
    model = BALFModel.load_from_checkpoint(config.path_to_model, num_classes=config.num_classes, learning_rate=config.learning_rate)

    # Test the model
    trainer.test(model, datamodule=data_module)

    return None


def predict_main():

    path_to_model = config.path_to_model
    path_to_images = config.path_to_unannotated_images

    output_path = helper.create_directories_for_results(config.path_to_results, config.curr_res_name, config.subdirs)

    model = ModelInference(path_to_model, path_to_images)

    model.perform_inference(output_path)

    return None


if __name__ == '__main__':
    
    if 'train_and_test' in config.modes:
        train_and_test_main()
    elif 'test' in config.modes:
        test_main()
    elif 'predict' in config.modes:
        predict_main()
        