#! /usr/bin/python
# -*- coding: utf-8 -*-

import tensorflow as tf

from tensorlayer.layers.core import Layer

from tensorlayer.layers.utils import cabs
from tensorlayer.layers.utils import quantize_active
from tensorlayer.layers.utils import quantize_weight

from tensorlayer import logging

from tensorlayer.decorators import deprecated_alias
from tensorlayer.decorators import force_return_self

__all__ = ['DorefaConv2d']


class DorefaConv2d(Layer):
    """The :class:`DorefaConv2d` class is a binary fully connected layer, which weights are 'bitW' bits and the output of the previous layer
    are 'bitA' bits while inferencing.

    Note that, the bias vector would not be binarized.

    Parameters
    ----------
    prev_layer : :class:`Layer`
        Previous layer.
    bitW : int
        The bits of this layer's parameter
    bitA : int
        The bits of the output of previous layer
    n_filter : int
        The number of filters.
    filter_size : tuple of int
        The filter size (height, width).
    strides : tuple of int
        The sliding window strides of corresponding input dimensions.
        It must be in the same order as the ``shape`` parameter.
    act : activation function
        The activation function of this layer.
    padding : str
        The padding algorithm type: "SAME" or "VALID".
    use_gemm : boolean
        If True, use gemm instead of ``tf.matmul`` for inferencing. (TODO).
    W_init : initializer
        The initializer for the the weight matrix.
    b_init : initializer or None
        The initializer for the the bias vector. If None, skip biases.
    W_init_args : dictionary
        The arguments for the weight matrix initializer.
    b_init_args : dictionary
        The arguments for the bias vector initializer.
    use_cudnn_on_gpu : bool
        Default is False.
    data_format : str
        "NHWC" or "NCHW", default is "NHWC".
    name : str
        A unique layer name.

    Examples
    ---------
    >>> import tensorflow as tf
    >>> import tensorlayer as tl
    >>> x = tf.placeholder(tf.float32, [None, 256, 256, 3])
    >>> net = tl.layers.InputLayer(x, name='input')
    >>> net = tl.layers.DorefaConv2d(net, 32, (5, 5), (1, 1), padding='SAME', name='bcnn1')
    >>> net = tl.layers.MaxPool2d(net, (2, 2), (2, 2), padding='SAME', name='pool1')
    >>> net = tl.layers.BatchNormLayer(net, act=tl.act.htanh, is_train=True, name='bn1')
    ...
    >>> net = tl.layers.SignLayer(net)
    >>> net = tl.layers.DorefaConv2d(net, 64, (5, 5), (1, 1), padding='SAME', name='bcnn2')
    >>> net = tl.layers.MaxPool2d(net, (2, 2), (2, 2), padding='SAME', name='pool2')
    >>> net = tl.layers.BatchNormLayer(net, act=tl.act.htanh, is_train=True, name='bn2')

    """

    @deprecated_alias(layer='prev_layer', end_support_version=1.9)  # TODO remove this line for the 1.9 release
    def __init__(
            self,
            prev_layer=None,
            bitW=1,
            bitA=3,
            n_filter=32,
            filter_size=(3, 3),
            strides=(1, 1),
            padding='SAME',
            use_gemm=False,
            use_cudnn_on_gpu=False,
            data_format=None,
            W_init=tf.truncated_normal_initializer(stddev=0.02),
            b_init=tf.constant_initializer(value=0.0),
            W_init_args=None,
            b_init_args=None,
            act=None,
            name='dorefa_cnn2d',
    ):

        # TODO: Implement GEMM
        if use_gemm:
            raise Exception("TODO. The current version use tf.matmul for inferencing.")

        if len(strides) != 2:
            raise ValueError("len(strides) should be 2.")

        self.prev_layer = prev_layer
        self.bitW = bitW
        self.bitA = bitA
        self.n_filter = n_filter
        self.filter_size = filter_size
        self.strides = strides
        self.padding = padding
        self.use_gemm = use_gemm
        self.use_cudnn_on_gpu = use_cudnn_on_gpu
        self.data_format = data_format
        self.W_init = W_init
        self.b_init = b_init
        self.act = act
        self.name = name

        super(DorefaConv2d, self).__init__(W_init_args=W_init_args, b_init_args=b_init_args)

    def __str__(self):
        additional_str = []

        try:
            additional_str.append("n_filter: %d" % self.n_filter)
        except AttributeError:
            pass

        try:
            additional_str.append("filter_size: %s" % str(self.filter_size))
        except AttributeError:
            pass

        try:
            additional_str.append("strides: %s" % str(self.strides))
        except AttributeError:
            pass

        try:
            additional_str.append("padding: %s" % self.padding)
        except AttributeError:
            pass

        try:
            additional_str.append("act: %s" % self.act.__name__ if self.act is not None else 'No Activation')
        except AttributeError:
            pass

        return self._str(additional_str)

    @force_return_self
    def __call__(self, prev_layer, is_train=True):

        super(DorefaConv2d, self).__call__(prev_layer)

        try:
            input_channels = int(self.inputs.get_shape()[-1])

        except TypeError:  # if input_channels is ?, it happens when using Spatial Transformer Net
            input_channels = 1
            logging.warning("unknown input channels, set to 1")

        quantized_inputs = quantize_active(cabs(self.inputs), self.bitA)  # Do not remove

        w_shape = (self.filter_size[0], self.filter_size[1], input_channels, self.n_filter)
        strides = (1, self.strides[0], self.strides[1], 1)

        with tf.variable_scope(self.name):
            W = self._get_tf_variable(
                name='W_conv2d', shape=w_shape, initializer=self.W_init, dtype=quantized_inputs.dtype, **self.W_init_args
            )

            W = quantize_weight(W, self.bitW)

            self.outputs = tf.nn.conv2d(
                quantized_inputs, W, strides=strides, padding=self.padding, use_cudnn_on_gpu=self.use_cudnn_on_gpu,
                data_format=self.data_format
            )

            if self.b_init:
                b = self._get_tf_variable(
                    name='b_conv2d', shape=(w_shape[-1]), initializer=self.b_init, dtype=quantized_inputs.dtype,
                    **self.b_init_args
                )

                self.outputs = tf.nn.bias_add(self.outputs, b, name='bias_add')

            self.outputs = self._apply_activation(self.outputs)

        self._add_layers(self.outputs)
        self._add_params(self._local_weights)
