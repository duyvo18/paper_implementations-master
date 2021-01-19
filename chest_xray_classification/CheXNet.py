# Implementation of "CheXNet: Radiologist-Level Pneumonia Detection on Chest X-Rays with Deep Learning", 2017,
# Pranav Rajpurkar, ..., Andrew Y. Ng
#
# https://arxiv.org/pdf/1711.05225.pdf

import os
os.environ['KERAS_BACKEND'] = 'tensorflow'

from weighted_binary_loss import WeightedBinaryLoss

from keras.applications import densenet
from keras.models import Model
from keras.layers import Dense, Input, GlobalAveragePooling2D
from keras.preprocessing.image import ImageDataGenerator
from keras.callbacks import ModelCheckpoint, ReduceLROnPlateau
import glob


class CheXNet:
    def __init__(self):
        # Final dense layer will have single output since this is binary classification problem
        self.output_classes = 1

        # Following hyper-params are set as per the paper
        self.input_size = 224
        self.batch_size = 16
        self.decay_factor = 1.0/10.0

        self.val_batch_size = 64  # This can be set any convenient value as per GPU capacity

        # Following will be set by get_data_stats() based on the dataset
        self.w_class0 = None
        self.w_class1 = None
        self.train_steps = None
        self.val_steps = None

        # get_model() will initialize this to DenseNet121 model
        self.model = None

    def get_data_stats(self, train_data_path, val_data_path, class_map):
        """
        Computes normal Vs Pneumonia class distribution

        :param train_data_path: path to training data. Samples os each class should be stored in separate folders
        :param val_data_path: path to validation data. Samples os each class should be stored in separate folders
        :param class_map: mapping of class index to folder names
        """

        # Count images in each class
        cls_cnts = [0] * len(class_map)
        for key, value in class_map.items():
            imgs = glob.glob(train_data_path + '/' + value + "/*")
            cls_cnts[key] = len(imgs)

        # compute class distribution
        self.w_class1 = float(cls_cnts[0])/sum(cls_cnts)
        self.w_class0 = float(cls_cnts[1])/sum(cls_cnts)

        # For convenience at train time, compute number of steps required to complete an epoch
        val_img_cnt = 0
        for key, value in class_map.items():
            imgs = glob.glob(val_data_path + '/' + value + "/*")
            val_img_cnt += len(imgs)

        self.train_steps = (sum(cls_cnts) // self.batch_size) + 1
        self.val_steps = (val_img_cnt // self.val_batch_size) + 1

    def get_model(self):
        """
        Create and compile the DenseNet121 model

        :return: DenseNet121 Model
        """

        # DenseNet121 expects number of channels to be 3
        input = Input(shape=(self.input_size, self.input_size, 3))

        base_pretrained_model = densenet.DenseNet121(input_shape=(self.input_size, self.input_size, 3),
                                                     input_tensor=input, include_top=False, weights='imagenet')
        x = GlobalAveragePooling2D()(base_pretrained_model.layers[-1].output)
        x = Dense(self.output_classes, activation='sigmoid')(x)

        self.model = Model(inputs=input, outputs=x)

        # Using weighted binary loss has been suggested in the paper
        loss = WeightedBinaryLoss(self.w_class0, self.w_class1)

        # Note: default learning rate of 'adam' is 0.001 as required by the paper
        self.model.compile(optimizer='adam', loss=loss.compute_loss)
        return self.model

    @staticmethod
    def imagenet_preproc(x):
        # mean and std of Image net is taken from
        # https://github.com/DeepVoltaire/AutoAugment/issues/4
        x = x / 255.0
        x = x - [0.485, 0.456, 0.406]
        x = x / [0.229, 0.224, 0.225]
        return x

    def train(self, train_data_path, val_data_path, epochs, weights_path, class_map):
        """
        Train the model

        :param train_data_path: path to training data. Samples os each class should be stored in separate folders
        :param val_data_path: path to validation data. Samples os each class should be stored in separate folders
        :param epochs: Number of epochs to train
        :param weights_path: path where trained model weights need to be strored
        :param class_map: mapping of class index to folder names

        """

        # We need to provide 'classes' to flow_from_directory() to make sure class 0 is 'normal'
        # and class 1 is pneumonia
        class_names = [0] * len(class_map)
        for key, value in class_map.items():
            class_names[key] = value

        # Paper suggests following:
        # 1. resize image to 224 x 224
        # 2. Use random horizontal flipping for augmenting
        # 3. normalize based on the mean and standard deviation of images in the ImageNet training set
        train_datagen = ImageDataGenerator(horizontal_flip=True,
                                           preprocessing_function=self.imagenet_preproc)
        train_generator = train_datagen.flow_from_directory(
            train_data_path,
            classes=class_names,
            target_size=(self.input_size, self.input_size),
            batch_size=self.batch_size,
            class_mode='binary')
        val_datagen = ImageDataGenerator(preprocessing_function=self.imagenet_preproc)
        val_generator = val_datagen.flow_from_directory(
            val_data_path,
            classes=class_names,
            target_size=(self.input_size, self.input_size),
            batch_size=self.val_batch_size,
            class_mode='binary')

        # Paper suggests following:
        # 1. use an initial learning rate of 0.001 that is decayed by a factor of 10 each
        # time the validation loss plateaus after an epoch
        # 2. pick the model with the lowest validation loss

        checkpoint = ModelCheckpoint(weights_path + 'CheXNet.h5', monitor='val_loss', verbose=1,
                                     save_best_only=True, mode='min')
        reduceLROnPlat = ReduceLROnPlateau(monitor='val_loss', factor=self.decay_factor)

        callbacks = [checkpoint, reduceLROnPlat]

        model.fit(train_generator,
                    steps_per_epoch=self.train_steps,
                    epochs=epochs,
                    callbacks=callbacks,
                    validation_data=val_generator,
                    validation_steps=self.val_steps)


if __name__ == '__main__':
    train_data_path = "data/train/"
    val_data_path = "data/val/"
    test_data_path = "data/test/"
    class_map = {0:'NORMAL', 1:'PNEUMONIA'}
    epochs = 50
    weights_path = "weights/"

    chexNet = CheXNet()
    # Compute normal Vs Pneumonia class distribution
    chexNet.get_data_stats(train_data_path, val_data_path, class_map)
    # Create and compile the DenseNet121 model
    model = chexNet.get_model()
    model.summary()

    # Train the model
    chexNet.train(train_data_path, val_data_path, epochs, weights_path, class_map)
