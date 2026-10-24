import torch
import common.helper_plot as helper_plot
import pytorch_lightning as pl
import matplotlib.pyplot as plt
from torchvision.models.detection import fasterrcnn_resnet50_fpn, FasterRCNN_ResNet50_FPN_Weights, faster_rcnn


class BALFModel(pl.LightningModule):

    def __init__(self, num_classes=2, learning_rate=1e-3):
        super().__init__()

        # Load the pre-trained model
        self.model = fasterrcnn_resnet50_fpn(weights=FasterRCNN_ResNet50_FPN_Weights.DEFAULT)

        # Get the number of input features for the classifier
        in_features = self.model.roi_heads.box_predictor.cls_score.in_features

        # Replace the pre-trained head with a new one for your specific number of classes
        self.model.roi_heads.box_predictor = faster_rcnn.FastRCNNPredictor(in_features, num_classes)

        # Setting Learning rate
        self.learning_rate = learning_rate

        # Setting device
        device = torch.device('cpu') # FIXME in every script set device in right way: 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model.to(device)


    def forward(self, images, targets=None):

        return self.model(images, targets)


    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.learning_rate)
        return optimizer


    def training_step(self, batch, batch_idx):

        images, targets = batch
        loss_dict = self.forward(images, targets)

        total_loss = sum(loss for loss in loss_dict.values())

        total_loss = self._common_log(loss_dict, 'train', len(batch))

        return total_loss


    def validation_step(self, batch, batch_idx):

        images, targets = batch

        # To calculate the loss during validation like in training
        self.model.train()
        with torch.no_grad():
            loss_dict = self.forward(images, targets)
        self.model.eval()        

        total_loss = self._common_log(loss_dict, 'val', len(batch))

        return total_loss

    
    def test_step(self, batch, batch_idx):

        images, targets = batch

        # To calculate the loss during testing like in training
        self.model.train()
        with torch.no_grad():
            loss_dict = self.forward(images, targets)
        self.model.eval()     

        total_loss = self._common_log(loss_dict, 'test', len(batch))

        with torch.no_grad():
            predictions = self.forward(images, targets)

        for i, (img, pred, target) in enumerate(zip(images, predictions, targets)):
            fig = helper_plot.visualize_test(img, pred, target)
            self.logger.experiment.add_figure(f'Testing_visualization', fig, global_step=self.global_step+i)
            plt.close(fig)

        return total_loss
    

    def _common_log(self, loss_dict, stage, batch_size):
    
        # self.log(f'{stage}_loss_classifier', loss_dict['loss_classifier'], on_step=False, on_epoch=True)
        # self.log(f'{stage}_loss_box_reg', loss_dict['loss_box_reg'], on_step=False, on_epoch=True)
        # self.log(f'{stage}_loss_objectness', loss_dict['loss_objectness'], on_step=False, on_epoch=True)
        # self.log(f'{stage}_loss_rpn_box_reg', loss_dict['loss_rpn_box_reg'], on_step=False, on_epoch=True)

        total_loss = sum(loss for loss in loss_dict.values())

        self.log(f'{stage}_total_loss', total_loss, on_step=False, on_epoch=True, 
                prog_bar=True, logger=True, batch_size=batch_size)
        
        return total_loss


