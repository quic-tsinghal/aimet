# !/usr/bin/env python
# =============================================================================
#  @@-COPYRIGHT-START-@@
#
#  Copyright (c) 2021, Qualcomm Innovation Center, Inc. All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
#  1. Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#
#  2. Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
#  3. Neither the name of the copyright holder nor the names of its contributors
#     may be used to endorse or promote products derived from this software
#     without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#  ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
#  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.
#
#  SPDX-License-Identifier: BSD-3-Clause
#
#  @@-COPYRIGHT-END-@@
# =============================================================================

"""
This file demonstrates the use of compression using AIMET spatial SVD
technique followed by fine tuning.
"""


import argparse
import os
from decimal import Decimal
import torch
from torchvision import models
from datetime import datetime
import logging

# imports for AIMET
from aimet_torch.compress import ModelCompressor
import aimet_torch.defs
import aimet_common.defs
from aimet_common.defs import CompressionScheme
from aimet_common.defs import CostMetric

# imports for data pipelines
from Examples.common import image_net_config
from Examples.torch.utils.image_net_evaluator import ImageNetEvaluator
from Examples.torch.utils.image_net_trainer import ImageNetTrainer

logger = logging.getLogger('TorchSpatialSVD')
formatter = logging.Formatter('%(asctime)s : %(name)s - %(levelname)s - %(message)s')
logging.basicConfig(format=formatter)


###
# data_pipelines_pytorch is a package internally developed by the CR&D Morpheus team.
# It provides utilities with which you can easily create training pipelines using
# the PyTorch framework. It also provides visualization of computational graph meta-data like
# number of parameters involved and MAC count estimate.

# This script utilize AIMET do perform spatial svd compression (50% ratio) on a resnet18 pretrained model
# with the ImageNet data set.   It should re-create the same performance numbers as published in the
# AIMET release for the particular scenario as described below.
#
# Scenario parameters:
#    - AIMET Spatial SVD compression using auto mode
#    - Ignored model.conv1 (this is the first layer of the model)
#    - Target compression ratio: 0.5 (or 50%)
#    - Number of compression ration candidates: 10
#    - Input shape: [1, 3, 224, 224]
#    - Learning rate: 0.01
#    - Learning rate schedule: [5,10]
###

class ImageNetDataPipeline:
    """
    Provides APIs for model compression using AIMET weight SVD, evaluation and finetuning.
    """

    def __init__(self, _config:argparse.Namespace):
        """
        :param _config:
        """
        self._config = _config


    def evaluate(self, model: torch.nn.Module, iterations: int = None, use_cuda: bool = False) -> float:
        """
        Evaluate the specified model using the specified number of samples from the validation set.
        AIMET's compress_model() expects the function with this signature to its eval_callback
        parameter.

        :param model: The model to be evaluated.
        :param iterations: The number of batches of the dataset.
        :param use_cuda: If True then use a GPU for inference.
        :return: The accuracy for the sample with the maximum accuracy.
        """

        # your code goes here instead of the example from below

        evaluator = ImageNetEvaluator(self._config.dataset_dir, image_size=image_net_config.dataset['image_size'],
                                      batch_size=image_net_config.evaluation['batch_size'],
                                      num_workers=image_net_config.evaluation['num_workers'])

        return evaluator.evaluate(model, iterations, use_cuda)


    def finetune(self, model: torch.nn.Module):
        """
        Finetunes the model.  The implemtation provided here is just an example,
        provide your own implementation if needed.

        :param model: The model to finetune.
        """

        # Your code goes here instead of the example from below

        trainer = ImageNetTrainer(self._config.dataset_dir, image_size=image_net_config.dataset['image_size'],
                                  batch_size=image_net_config.train['batch_size'],
                                  num_workers=image_net_config.train['num_workers'])

        trainer.train(model, max_epochs=self._config.epochs, learning_rate=self._config.learning_rate,
                      learning_rate_schedule=self._config.learning_rate_schedule, use_cuda=self._config.use_cuda)


        torch.save(model, os.path.join(self._config.logdir, 'finetuned_model.pth'))

def aimet_spatial_svd(model: torch.nn.Module,
                     evaluator: aimet_common.defs.EvalFunction):
    """
    Compresses the model using AIMET's Spatial SVD auto mode compression scheme.

    :param model: The model to compress
    :param evaluator: Evaluator used during compression
    :param data_loader: DataLoader used during compression
    :return: A tuple of compressed model and its statistics
    """


    # create the parameters for AIMET to compress on auto mode.
    # please refer to the API documentation for other schemes (i.e weight svd & channel prunning)
    # and mode (manual)
    greedy_params = aimet_torch.defs.GreedySelectionParameters(target_comp_ratio=Decimal(0.5),
                                                               num_comp_ratio_candidates=10)
    auto_params = aimet_torch.defs.SpatialSvdParameters.AutoModeParams(greedy_params,
                                                                       modules_to_ignore=[model.conv1])
    params = aimet_torch.defs.SpatialSvdParameters(aimet_torch.defs.SpatialSvdParameters.Mode.auto,
                                                   auto_params)

    scheme = CompressionScheme.spatial_svd      # spatial_svd, weight_svd or channel_pruning
    metric = CostMetric.mac                     # mac or memory

    results = ModelCompressor.compress_model(model=model,
                                             eval_callback=evaluator,
                                             eval_iterations=10,
                                             input_shape=(1, 3, 224, 224),
                                             compress_scheme=scheme,
                                             cost_metric=metric,
                                             parameters=params)
    return results

def compress_and_finetune(config: argparse.Namespace):
    """
    1. Instantiate Data Pipeline for evaluation and training
    2. Load the pretrained resnet18 model
    3. Calculate floating point accuracy
    4. Compression
        4.1. Compress the model using AIMET Spatial SVD
        4.2. Log the statistics
        4.3. Save the compressed model
        4.4. Calculate and log the accuracy of compressed model
    5. Finetuning
        5.1 Finetune the compressed model
        5.2 Calculate and log the accuracy of compressed-finetuned model

    :param config: This argparse.Namespace config expects following parameters:
                   dataset_dir: Path to a directory containing ImageNet dataset.
                                This folder should conatin at least 2 subfolders:
                                'train': for training dataset and 'val': for validation dataset.
                   use_cuda: A boolean var to indicate to run the test on GPU.
                   logdir: Path to a directory for logging.
                   epochs: Number of epochs (type int) for finetuning.
                   learning_rate: A float type learning rate for model finetuning
                   learning_rate_schedule: A list of epoch indices for learning rate schedule used in finetuning. Check
                                           https://pytorch.org/docs/stable/_modules/torch/optim/lr_scheduler.html#MultiStepLR
                                           for more details.
    """

    # Instantiate Data Pipeline for evaluation and training
    data_pipeline = ImageNetDataPipeline(config)


    # Loads the pretrained resnet18 model
    model = models.resnet18(pretrained=True)
    if config.use_cuda:
        model.to(torch.device('cuda'))


    # Calculates floating point accuracy
    accuracy = data_pipeline.evaluate(model, use_cuda=config.use_cuda)
    logger.info("Original Model Top-1 accuracy = %.2f", accuracy)


    # Compression
    logger.info("Starting Model Compression...")

    # Compress the model using AIMET Weight SVD
    compressed_model, stats = aimet_spatial_svd(model=model, evaluator=data_pipeline.evaluate)

    # Log the statistics
    logger.info(stats)
    with open(os.path.join(config.logdir, 'log.txt'), "w") as outfile:
        outfile.write("%s\n\n" % (stats))

    # Saves the compressed model
    torch.save(compressed_model, os.path.join(config.logdir, 'compressed_model.pth'))

    # Calculates and logs the accuracy of compressed model
    accuracy = data_pipeline.evaluate(compressed_model, use_cuda=config.use_cuda)
    logger.info("Compressed Model Top-1 accuracy = %.2f", accuracy)

    logger.info("...Model Compression Complete")


    # Finetuning
    logger.info("Strating Model Finetuning...")

    # Finetune the compressed model
    data_pipeline.finetune(compressed_model)

    # Calculate and log the accuracy of compressed-finetuned model
    accuracy = data_pipeline.evaluate(compressed_model, use_cuda=config.use_cuda)
    logger.info("Finetuned Compressed Model Top-1 accuracy = %.2f", accuracy)

    logger.info("...Model Finetuning Complete")


if __name__ == '__main__':
    default_logdir = os.path.join("benchmark_output", "spatial_svd_"+datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

    parser = argparse.ArgumentParser(description='Apply Weight SVD on pretrained ResNet18 model and finetune it for ImageNet dataset')

    parser.add_argument('--dataset_dir', type=str,
                        required=True,
                        help="Path to a directory containing ImageNet dataset.\n\
                              This folder should conatin at least 2 subfolders:\n\
                              'train': for training dataset and 'val': for validation dataset")
    parser.add_argument('--use_cuda', action='store_true',
                        required=True,
                        help='Add this flag to run the test on GPU.')

    parser.add_argument('--logdir', type=str,
                        default=default_logdir,
                        help="Path to a directory for logging.\
                              Default value is 'benchmark_output/weight_svd_<Y-m-d-H-M-S>'")

    parser.add_argument('--epochs', type=int,
                        default=15,
                        help="Number of epochs for finetuning.\n\
                              Default is 15")
    parser.add_argument('--learning_rate', type=float,
                        default=1e-2,
                        help="A float type learning rate for model finetuning.\n\
                              default is 0.01")
    parser.add_argument('--learning_rate_schedule', type=list,
                        default=[5, 10],
                        help="A list of epoch indices for learning rate schedule used in finetuning.\n\
                              Check https://pytorch.org/docs/stable/_modules/torch/optim/lr_scheduler.html#MultiStepLR for more details.\n\
                              default is [5, 10]")

    _config = parser.parse_args()

    os.makedirs(_config.logdir, exist_ok=True)

    fileHandler = logging.FileHandler(os.path.join(_config.logdir, "test.log"))
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)

    if _config.use_cuda and not torch.cuda.is_available():
        logger.error('use_cuda is selected but no cuda device found.')
        raise RuntimeError("Found no CUDA Device while use_cuda is selected")

    compress_and_finetune(_config)
