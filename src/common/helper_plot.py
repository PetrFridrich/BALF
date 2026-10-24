import matplotlib.pyplot as plt

import common.mapping as m


def visualize_test(img, pred, target):

    fig, axs = plt.subplots(1, 2, figsize=(12, 6))

    img = img.permute(1, 2, 0).cpu().numpy()

    # Image 1
    axs[0].imshow(img)
    axs[0].set_title('Model prediction', fontsize=20, pad=10)

    axs[0].axis('off')

    pred_boxes = pred['boxes'].cpu().numpy()
    pred_labels = pred['labels'].cpu().numpy()

    for box, label in zip(pred_boxes, pred_labels):
        axs[0].add_patch(plt.Rectangle((box[0], box[1]), box[2] - box[0], box[3] - box[1], fill=False, edgecolor=m.map_lbl_to_clr.get(label, 'black'), linewidth=1, alpha=0.5))
        axs[0].text(box[0], box[1], f'{m.map_lbl_to_name.get(label, 'Undefined')}', color='black', fontsize=5, bbox=dict(facecolor=f'{m.map_lbl_to_clr.get(label, 'black')}', alpha=0.5, pad=0.2, edgecolor='none', linewidth=0))

    # Image 2
    axs[1].imshow(img)
    axs[1].set_title('Original image with targets', fontsize=20, pad=5)

    axs[1].axis('off')

    target_boxes = target['boxes'].cpu().numpy()
    target_labels = target['labels'].cpu().numpy()

    for box, label in zip(target_boxes, target_labels):
        axs[1].add_patch(plt.Rectangle((box[0], box[1]), box[2] - box[0], box[3] - box[1], fill=False, edgecolor=m.map_lbl_to_clr.get(label, 'black'), linewidth=1, alpha=0.5))
        axs[1].text(box[0], box[1], f'{m.map_lbl_to_name.get(label, 'Undefined')}', color='black', fontsize=5, bbox=dict(facecolor=f'{m.map_lbl_to_clr.get(label, 'black')}', alpha=0.5, pad=0.2, edgecolor='none', linewidth=0))
    
    plt.tight_layout(pad=0.2)

    return fig


def visualize_prediction(img, pred, output_path):

    pred_boxes = pred[0]['boxes'].cpu().numpy().astype(int)
    pred_labels = pred[0]['labels'].cpu().numpy().astype(int)

    fig, axs = plt.subplots(1, 2, figsize=(36, 18))

    # Image 1
    axs[0].imshow(img)
    axs[0].set_title('Model Prediction', fontsize=20, pad=20)

    axs[0].axis('off')

    for box, label in zip(pred_boxes, pred_labels):
        axs[0].add_patch(plt.Rectangle((box[0], box[1]), box[2] - box[0], box[3] - box[1], fill=False, edgecolor=m.map_lbl_to_clr.get(label, 'black'), linewidth=1, alpha=0.5))
        axs[0].text(box[0], box[1], f'{m.map_lbl_to_name.get(label, 'Undefined')}', color='black', fontsize=5, bbox=dict(facecolor=f'{m.map_lbl_to_clr.get(label, 'black')}', alpha=0.5, pad=0.2, edgecolor='none', linewidth=0))

    # Image 2
    axs[1].imshow(img)
    axs[1].set_title('Original image', fontsize=20, pad=20)

    axs[1].axis('off')
    
    plt.savefig(output_path, bbox_inches='tight', pad_inches=0.2)
    plt.close(fig)

    return None

