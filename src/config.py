from pathlib import Path

modes = ['predict']

# Data Module
path_images = Path('./data/images/')
path_annotations = Path('./data/annotations/')
batch_size=2
num_of_workers=0
train_ratio=0.6

# Logger
log_dir = Path('./tb_logs/')
name = 'R-CNN_model'

# Trainer
max_epochs = 100

# Model
learning_rate = 1e-4
num_classes = 2

# Prediction paths
path_to_model = Path('./tb_logs/R-CNN_model/version_0/checkpoints/epoch=99-step=300.ckpt')
path_to_unannotated_images = Path('./data/unannotated_images/')

path_to_results = Path('./results/')
curr_res_name = 'Predict'
subdirs = ['visualization', 'labels']




