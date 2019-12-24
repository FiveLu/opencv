import cv2 as cv
import numpy as np
import argparse


backends = (cv.dnn.DNN_BACKEND_DEFAULT, cv.dnn.DNN_BACKEND_HALIDE,
            cv.dnn.DNN_BACKEND_OPENCV, cv.dnn.DNN_BACKEND_INFERENCE_ENGINE)
targets = (cv.dnn.DNN_TARGET_CPU, cv.dnn.DNN_TARGET_OPENCL, cv.dnn.DNN_TARGET_OPENCL_FP16, cv.dnn.DNN_TARGET_MYRIAD)

parser = argparse.ArgumentParser(description='Use this script to run human parsing using JPPNet',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--input', '-i', help='Path to input image. Skip this argument to capture frames from a camera.')
parser.add_argument('--model', '-m', required=True, help='Path to pb model.')
parser.add_argument('--backend', choices=backends, default=cv.dnn.DNN_BACKEND_DEFAULT, type=int,
                    help="Choose one of computation backends: "
                         "%d: automatically (by default), "
                         "%d: Halide language (http://halide-lang.org/), "
                         "%d: Intel's Deep Learning Inference Engine (https://software.intel.com/openvino-toolkit), "
                         "%d: OpenCV implementation" % backends)
parser.add_argument('--target', choices=targets, default=cv.dnn.DNN_TARGET_CPU, type=int,
                    help='Choose one of target computation devices: '
                         '%d: CPU target (by default), '
                         '%d: OpenCL, '
                         '%d: OpenCL fp16 (half-float precision), '
                         '%d: VPU' % targets)

# To get pre-trained model download https://drive.google.com/file/d/1BFVXgeln-bek8TCbRjN6utPAgRE0LJZg/view
# For correct convert .meta to .pb model download original repository https://github.com/Engineering-Course/LIP_JPPNet
# Change script evaluate_parsing_JPPNet-s2.py for human parsing
# 1. Remove preprocessing to create image_batch_origin:
# - with tf.name_scope("create_inputs"):
#     ...
# Add
# -    image_batch_origin = tf.placeholder(tf.float32, shape=(2, None, None, 3), name='input')
#
# 2. Create input
#     image = cv2.imread(path/to/image)
#     image_rev = np.flip(image, axis=1)
#     image_h, image_w = image.shape[:2]
#     input = np.stack([image, image_rev], axis=0)
#
# 3. Hardcode image_h and image_w shapes to determine output shapes
# -   parsing_out1 = tf.reduce_mean(tf.stack([tf.image.resize_images(parsing_out1_100, [image_h, image_w]),
#                                        tf.image.resize_images(parsing_out1_075, [image_h, image_w]),
#                                        tf.image.resize_images(parsing_out1_125, [image_h, image_w])]), axis=0)
#     Do similarly with parsing_out2, parsing_out3
# 4. Remove postprocessing
# -    parsing_ = sess.run(raw_output, feed_dict={'input:0': input})
#
# 5. To save model after sess.run(...) add:
# -    input_graph_def = tf.get_default_graph().as_graph_def()
# -    output_node = "Mean_3"
# -    output_graph_def = tf.graph_util.convert_variables_to_constants(sess, input_graph_def, output_node)
# -
# -    output_graph = "LIP_JPPNet.pb"
# -    with tf.gfile.GFile(output_graph, "wb") as f:
# -        f.write(output_graph_def.SerializeToString())



def preprocess(image_path):
    """
    Create 4-dimensional blob from image and flip image
    :param image_path: path to input image
    """
    image = cv.imread(image_path)
    image_rev = np.flip(image, axis=1)
    input = cv.dnn.blobFromImages([image, image_rev], mean=(104.00698793, 116.66876762, 122.67891434))
    return input


def run_net(input, model_path, backend, target):
    """
    Read network and infer model
    :param model_path: path to JPPNet model
    """
    net = cv.dnn.readNet(model_path)
    net.setPreferableBackend(backend)
    net.setPreferableTarget(target)
    net.setInput(input)
    out = net.forward()
    return out


def postprocess(out):
    """
    Create a grayscale human segmentation
    :param out: network output
    """
    # LIP classes
    # 0 Background
    # 1 Hat
    # 2 Hair
    # 3 Glove
    # 4 Sunglasses
    # 5 UpperClothes
    # 6 Dress
    # 7 Coat
    # 8 Socks
    # 9 Pants
    # 10 Jumpsuits
    # 11 Scarf
    # 12 Skirt
    # 13 Face
    # 14 LeftArm
    # 15 RightArm
    # 16 LeftLeg
    # 17 RightLeg
    # 18 LeftShoe
    # 19 RightShoe
    head_output, tail_output = np.split(out, indices_or_sections=[1], axis=0)
    head_output = head_output.squeeze(0)
    tail_output = tail_output.squeeze(0)
    tail_list = np.split(tail_output, indices_or_sections=list(range(1, 20)), axis=0)
    tail_list = [arr.squeeze(0) for arr in tail_list]
    tail_list_rev = [tail_list[i] for i in range(14)]
    tail_list_rev.extend([tail_list[15], tail_list[14], tail_list[17], tail_list[16], tail_list[19], tail_list[18]])
    tail_output_rev = np.stack(tail_list_rev, axis=0)
    tail_output_rev = np.flip(tail_output_rev, axis=2)
    raw_output_all = np.mean(np.stack([head_output, tail_output_rev], axis=0), axis=0, keepdims=True)
    raw_output_all = np.argmax(raw_output_all, axis=1)
    raw_output_all = raw_output_all.transpose(1, 2, 0)
    return raw_output_all


def decode_labels(gray_image):
    """
    Colorize image according to labels
    :param gray_image: grayscale human segmentation result
    """
    height, width, _ = gray_image.shape
    colors = [(0, 0, 0), (128, 0, 0), (255, 0, 0), (0, 85, 0), (170, 0, 51), (255, 85, 0),
              (0, 0, 85), (0, 119, 221), (85, 85, 0), (0, 85, 85), (85, 51, 0), (52, 86, 128),
              (0, 128, 0), (0, 0, 255), (51, 170, 221), (0, 255, 255),(85, 255, 170),
              (170, 255, 85), (255, 255, 0), (255, 170, 0)]

    segm = np.stack([colors[idx] for idx in gray_image.flatten()])
    segm = segm.reshape(height, width, 3).astype(np.uint8)
    segm = cv.cvtColor(segm, cv.COLOR_BGR2RGB)
    return segm


def parse_human(image_path, model_path, backend, target):
    """
    Prepare input for execution, run net and postprocess output to parse human.
    :param image_path: path to input image
    :param model_path: path to JPPNet model
    :param backend: name of computation backend
    :param target: name of computation target
    """
    input = preprocess(image_path)
    output = run_net(input, model_path, backend, target)
    grayscale_out = postprocess(output)
    segmentation = decode_labels(grayscale_out)
    return segmentation


if __name__ == '__main__':
    args, _ = parser.parse_known_args()
    output = parse_human(args.input, args.model, args.backend, args.target)
    winName = 'Deep learning human parsing in OpenCV'
    cv.namedWindow(winName, cv.WINDOW_AUTOSIZE)
    cv.imshow(winName, output)
    cv.waitKey()
