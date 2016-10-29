
# Note! The basic structure of this neural network was primarily created using a tutorial found in the credits
# This is primarily a research project and I take no claim to the thought process behind the code below.
# I did change the code a lot to make it object oriented and a bit easier to follow as well as ported it to python 3

import numpy as np
import theano as theano
import theano.tensor as T
import operator
from datetime import datetime
import sys


class RNN:

    def __init__(self,word_to_index,index_to_word, word_dim,fname=None, hidden_dim=100, bptt_truncate=4):
        # Assign instance variables
        self.word_dim = word_dim
        self.hidden_dim = hidden_dim
        self.fname = fname
        self.word_to_index = word_to_index
        self.index_to_word = index_to_word
        self.bptt_truncate = bptt_truncate
        # Randomly initialize the network parameters
        U = np.random.uniform(-np.sqrt(1./word_dim), np.sqrt(1./word_dim), (hidden_dim, word_dim))
        V = np.random.uniform(-np.sqrt(1./hidden_dim), np.sqrt(1./hidden_dim), (word_dim, hidden_dim))
        W = np.random.uniform(-np.sqrt(1./hidden_dim), np.sqrt(1./hidden_dim), (hidden_dim, hidden_dim))
        # Theano: Created shared variables
        self.U = theano.shared(name='U', value=U.astype(theano.config.floatX))
        self.V = theano.shared(name='V', value=V.astype(theano.config.floatX))
        self.W = theano.shared(name='W', value=W.astype(theano.config.floatX))
        # We store the Theano graph here
        self.theano = {}
        self.__theano_build__()
        self.num_examples_seen = 0

    def __theano_build__(self):
        U, V, W = self.U, self.V, self.W
        x = T.ivector('x')
        y = T.ivector('y')
        def forward_prop_step(x_t, s_t_prev, U, V, W):
            s_t = T.tanh(U[:,x_t] + W.dot(s_t_prev))
            o_t = T.nnet.softmax(V.dot(s_t))
            return [o_t[0], s_t]
        [o,s], updates = theano.scan(
            forward_prop_step,
            sequences=x,
            outputs_info=[None, dict(initial=T.zeros(self.hidden_dim))],
            non_sequences=[U, V, W],
            truncate_gradient=self.bptt_truncate,
            strict=True)

        prediction = T.argmax(o, axis=1)
        o_error = T.sum(T.nnet.categorical_crossentropy(o, y))

        # Gradients
        dU = T.grad(o_error, U)
        dV = T.grad(o_error, V)
        dW = T.grad(o_error, W)

        # Assign functions
        self.forward_propagation = theano.function([x], o)
        self.predict = theano.function([x], prediction)
        self.ce_error = theano.function([x, y], o_error)
        self.bptt = theano.function([x, y], [dU, dV, dW])

        # SGD
        learning_rate = T.scalar('learning_rate')
        self.sgd_step = theano.function([x,y,learning_rate], [],
                      updates=[(self.U, self.U - learning_rate * dU),
                              (self.V, self.V - learning_rate * dV),
                              (self.W, self.W - learning_rate * dW)])

    def calculate_total_loss(self, X, Y):
        return np.sum([self.ce_error(x,y) for x,y in zip(X,Y)])

    def calculate_loss(self, X, Y):
        # Divide calculate_loss by the number of words
        num_words = np.sum([len(y) for y in Y])
        return self.calculate_total_loss(X,Y)/float(num_words)

    def train_with_sgd(self, X_train, y_train, learning_rate=0.005, nepoch=1, evaluate_loss_after=5):
        # We keep track of the losses so we can plot them later
        losses = []
        for epoch in range(nepoch):
            # Optionally evaluate the loss
            if (epoch % evaluate_loss_after == 0):
                loss = self.calculate_loss(X_train, y_train)
                losses.append((num_examples_seen, loss))
                time = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
                print("%s: Loss after num_examples_seen=%d epoch=%d: %f" % (time, self.num_examples_seen, epoch, loss) )
                if self.fname is not None:
                    self.save(self.fname)
                # Adjust the learning rate if loss increases
                if (len(losses) > 1 and losses[-1][1] > losses[-2][1]):
                    learning_rate = learning_rate * 0.5
                    print ("Setting learning rate to %f" % learning_rate)
                sys.stdout.flush()
            # For each training example...
            for i in range(len(y_train)):
                # One SGD step
                self.sgd_step(X_train[i], y_train[i], learning_rate)
            self.num_examples_seen += 1

    def save(self,outfile):
        U, V, W = self.U.get_value(), self.V.get_value(), self.W.get_value()
        np.savez(outfile, U=U, V=V, W=W)

    def load(self, path):
        npzfile = np.load(path)
        U, V, W = npzfile["U"], npzfile["V"], npzfile["W"]
        self.hidden_dim = U.shape[0]
        self.word_dim = U.shape[1]
        self.U.set_value(U)
        self.V.set_value(V)
        self.W.set_value(W)

    def gradient_check_theano(self, x, y, h=0.001, error_threshold=0.01):
        # Overwrite the bptt attribute. We need to backpropagate all the way to get the correct gradient
        self.bptt_truncate = 1000
        # Calculate the gradients using backprop
        bptt_gradients = self.bptt(x, y)
        # List of all parameters we want to chec.
        model_parameters = ['U', 'V', 'W']
        # Gradient check for each parameter
        for pidx, pname in enumerate(model_parameters):
            # Get the actual parameter value from the mode, e.g. model.W
            parameter_T = operator.attrgetter(pname)(self)
            parameter = parameter_T.get_value()
            print ("Performing gradient check for parameter %s with size %d." % (pname, np.prod(parameter.shape)))
            # Iterate over each element of the parameter matrix, e.g. (0,0), (0,1), ...
            it = np.nditer(parameter, flags=['multi_index'], op_flags=['readwrite'])
            while not it.finished:
                ix = it.multi_index
                # Save the original value so we can reset it later
                original_value = parameter[ix]
                # Estimate the gradient using (f(x+h) - f(x-h))/(2*h)
                parameter[ix] = original_value + h
                parameter_T.set_value(parameter)
                gradplus = self.calculate_total_loss([x],[y])
                parameter[ix] = original_value - h
                parameter_T.set_value(parameter)
                gradminus = self.calculate_total_loss([x],[y])
                estimated_gradient = (gradplus - gradminus)/(2*h)
                parameter[ix] = original_value
                parameter_T.set_value(parameter)
                # The gradient for this parameter calculated using backpropagation
                backprop_gradient = bptt_gradients[pidx][ix]
                # calculate The relative error: (|x - y|/(|x| + |y|))
                relative_error = np.abs(backprop_gradient - estimated_gradient)/(np.abs(backprop_gradient) + np.abs(estimated_gradient))
                # If the error is to large fail the gradient check
                if relative_error > error_threshold:
                    print("Gradient Check ERROR: parameter=%s ix=%s" % (pname, ix))
                    print("+h Loss: %f" % gradplus)
                    print("-h Loss: %f" % gradminus)
                    print("Estimated_gradient: %f" % estimated_gradient)
                    print("Backpropagation gradient: %f" % backprop_gradient)
                    print("Relative Error: %f" % relative_error)
                    return
                it.iternext()
                print("Gradient check for parameter %s passed." % (pname))

    def create_sentence(self):

        unknown_token = "UNKNOWN_TOKEN"
        sentence_start_token = "SENTENCE_START"
        sentence_end_token = "SENTENCE_END"
        new_sentence = [self.word_to_index[sentence_start_token]]

        while not new_sentence[-1] == self.word_to_index[sentence_end_token]:
            next_word_probs = self.forward_propagation(new_sentence)
            sampled_word = self.word_to_index[unknown_token]

            #while sampled_word == self.word_to_index[unknown_token]:
            samples = np.random.multinomial(1, next_word_probs[-1])
            sampled_word = np.argmax(samples)
            new_sentence.append(sampled_word)
            if(len(new_sentence) >= 3):
                sentence_str = [self.index_to_word[x] for x in new_sentence[1:-1]]
                print(" ".join(sentence_str))
        if(len(new_sentence) >= 3):
            sentence_str = [self.index_to_word[x] for x in new_sentence[1:-1]]
            return sentence_str
        else:
            print("Redoing create sentence")
            return create_sentence()
