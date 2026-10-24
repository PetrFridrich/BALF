from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import common.mapping as m


def create_directories_for_results(base_path, dir_name, sub_dirs):

    output_path = base_path / Path(dir_name)

    for i, sub_dir in enumerate(sub_dirs):
        dir = output_path / Path(sub_dir)
        dir.mkdir(parents=True, exist_ok=True)

    return output_path


def create_xml_annotation(pred, path_to_img, output_path, shape, folder = 'BALF_project'):

    # Extract cell_bbs and cell_types from pred
    cell_bbs = pred[0]['boxes'].cpu().numpy().astype(int)
    cell_types = pred[0]['labels'].cpu().numpy().astype(int)

    # Set filename
    filename = path_to_img.name
    
    # Zip cell_bbs and cell_types together and sort by [ymin, xmin]
    combined = sorted(zip(cell_bbs, cell_types), key=lambda x: (x[0][1], x[0][0]))

    # Unzip after sorting
    cell_bbs, cell_types = zip(*combined)

    # Create the root element
    root = ET.Element('annotation')

    # Create folder element
    folder_el = ET.SubElement(root, 'folder')
    folder_el.text = folder

    # Add filename element
    filename_el = ET.SubElement(root, 'filename')
    filename_el.text = filename

    # Add path element
    path_el = ET.SubElement(root, 'path')
    path_el.text = f'{folder}/{filename}'

    # Add source element
    source_el = ET.SubElement(root, 'source')
    database_el = ET.SubElement(source_el, 'database')
    database_el.text = 'Unspecified'

    # Add size element
    size_el = ET.SubElement(root, 'size')
    width_el = ET.SubElement(size_el, 'width')
    width_el.text = str(shape[1])
    height_el = ET.SubElement(size_el, 'height')
    height_el.text = str(shape[0])
    depth_el = ET.SubElement(size_el, 'depth')
    depth_el.text = str(shape[2])

    # Add object elements for each cell bounding box and type
    for bbox, cell_type in zip(cell_bbs, cell_types):
        object_el = ET.SubElement(root, 'object')

        name_el = ET.SubElement(object_el, 'name')
        name_el.text = m.map_lbl_to_name.get(cell_type, 'Undefined')

        pose_el = ET.SubElement(object_el, 'pose')
        pose_el.text = 'Unspecified'

        truncated_el = ET.SubElement(object_el, 'truncated')
        truncated_el.text = '0'

        difficult_el = ET.SubElement(object_el, 'difficult')
        difficult_el.text = '0'

        bndbox_el = ET.SubElement(object_el, 'bndbox')
        xmin_el = ET.SubElement(bndbox_el, 'xmin')
        xmin_el.text = str(bbox[0])
        ymin_el = ET.SubElement(bndbox_el, 'ymin')
        ymin_el.text = str(bbox[1])
        xmax_el = ET.SubElement(bndbox_el, 'xmax')
        xmax_el.text = str(bbox[2])
        ymax_el = ET.SubElement(bndbox_el, 'ymax')
        ymax_el.text = str(bbox[3])

    # Pretty print the XML
    xml_str = ET.tostring(root)
    pretty_xml = minidom.parseString(xml_str).toprettyxml(indent='    ')

    # Remove the XML declaration
    pretty_xml = '\n'.join(pretty_xml.split('\n')[1:])
    
    # Write to a file
    with open(f'{output_path / path_to_img.stem}.xml', 'w') as f:
        f.write(pretty_xml)

    