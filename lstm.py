import numpy as np
import theano
import theano.tensor as T
from process import process
from ipdb import set_trace as pause
from matplotlib import pyplot as plt
from hf import hf_optimizer
# This object contains the global network
def int_to_label(y, n_classes):

    result = np.zeros((y.shape[0], n_classes))
    for idx,i in enumerate(y):
        result[idx][int(i)] = 1
    return result


class LSTM(object):

    def __init__(self, n_in, n_layers, n_hidden, n_classes):
        print "Initialize LSTM network..."

        self.lr =0.1
        self.momentum = 0.9
        self.x = T.matrix()         # network input
        self.y = T.ivector()        # target labels (multiclass integer format)
        # Size parameters
        self.n_in = n_in            # input dimensionality
        self.n_hidden = n_hidden    # number of hidden units
        self.n_classes = n_classes  # number of output classes (softmax layer size)

        # Init a Single LSTM Layer
        self.lstm_layer = LSTM_layer(self.x, n_in, n_hidden)

        # Init a Softmax Layer for Output
        self.softmax_layer = Softmax_layer(self.lstm_layer.h, n_hidden, n_classes)

        # Declare parameters for LSTM network
        self.params = [self.lstm_layer.W_i, self.lstm_layer.W_c, self.lstm_layer.W_f, self.lstm_layer.W_o, self.lstm_layer.U_i,
                       self.lstm_layer.U_f, self.lstm_layer.U_c, self.lstm_layer.V_o, self.lstm_layer.bi, self.lstm_layer.bf,
                       self.lstm_layer.bc, self.lstm_layer.bo, self.lstm_layer.h0]

        self.cross_entropy_cost = T.mean(T.nnet.categorical_crossentropy(self.softmax_layer.p_y_given_x, self.y))
        self.nll_cost = self.nll_multiclass(self.y)
        self.grad_cost = T.grad(self.nll_cost, self.params)
        self.nll_cost_fn = theano.function(inputs=[self.x, self.y], outputs=self.nll_cost)
        self.cross_entropy_cost_fn = theano.function(inputs=[self.x, self.y], outputs=self.cross_entropy_cost)
        self.grad_cost_fn =theano.function(inputs=[self.x, self.y], outputs= self.grad_cost)
        self.predict_fn = theano.function(inputs=[self.x], outputs=self.softmax_layer.y_pred)

        print "Initialization of LSTM network done!"

    def train(self, gradient_dataset):
        """     
        :param x: Train an example n_steps * m_features
        :param y: n_steps * 1
        :return:
        """

        result =[np.zeros(i.get_value().shape) for i in self.params]
        for inputs in gradient_dataset.iterate(update=True):
            result =[i+j for i, j in zip(result, self.grad_cost_fn(inputs[0],inputs[1]))]

        result = [i/float(gradient_dataset.number_batches) for i in result]

        # Update all parameters
        updates = [i.get_value()-self.lr*j for i,j in zip(self.params,result)]
        for i in range(len(self.params)):
            self.params[i].set_value(updates[i])
            #self.params[i].set_value(self.params[i].get_value()+10)


        for i in self.params:
            print str(i)+" "+str(np.max(i.get_value()))+ " "+str(np.min(i.get_value()))+" "+str(np.mean(i.get_value()))

        # Evaluate the cost at this epoch
        mean_cross_entropy_cost = 0
        mean_nll_cost  = 0
        for inputs in  gradient_dataset.iterate(update=True):
            mean_cross_entropy_cost += self.cross_entropy_cost_fn(inputs[0],inputs[1])
            mean_nll_cost += self.nll_cost_fn(inputs[0],inputs[1])

        mean_cross_entropy_cost = mean_cross_entropy_cost/gradient_dataset.number_batches
        mean_nll_cost = mean_nll_cost/gradient_dataset.number_batches

        print " Cost : "+str(mean_cross_entropy_cost)+" "+str(mean_nll_cost)

    def predict(self,X):
        return self.predict_fn(X)

    def plot_param(self,idx):
        plt.close()
        plt.imshow(np.abs(self.params[idx].get_value()),cmap=plt.get_cmap('gray'))
        plt.show()

    def nll_multiclass(self, y):
        # negative log likelihood based on multiclass cross entropy error
        # y.shape[0] is (symbolically) the number of rows in y, i.e.,
        # number of time steps (call it T) in the sequence
        # T.arange(y.shape[0]) is a symbolic vector which will contain
        # [0,1,2,... n-1] T.log(self.p_y_given_x) is a matrix of
        # Log-Probabilities (call it LP) with one row per example and
        # one column per class LP[T.arange(y.shape[0]),y] is a vector
        # v containing [LP[0,y[0]], LP[1,y[1]], LP[2,y[2]], ...,
        # LP[n-1,y[n-1]]] and T.mean(LP[T.arange(y.shape[0]),y]) is
        # the mean (across minibatch examples) of the elements in v,
        # i.e., the mean log-likelihood across the minibatch.
        return -T.mean(T.log(self.softmax_layer.p_y_given_x)[T.arange(y.shape[0]), y])

    def list_to_flat(self, l):
        return np.concatenate([i.flatten() for i in l])


class Softmax_layer(object):

    def __init__(self, xt,n_in, n_classes):
        # Not sure if shared_variable.shape works but it seems so
        W_soft_init = np.asarray(np.random.uniform(size=(n_in,n_classes),
                                          low=-.01, high=.01),
                                          dtype=theano.config.floatX)
        self.W_soft = theano.shared(value=W_soft_init,name='W_soft')
        b_soft_init = np.asarray(np.zeros(n_classes))
        self.b_soft = theano.shared(value = b_soft_init, name='b_soft')
        self.xt = xt
        self.n_classes = n_classes

        def symbolic_softmax(x):
                e = T.exp(x)
                return e / T.sum(e, axis=1).dimshuffle(0, 'x')
        self.y_out = T.dot(self.xt,self.W_soft)
        self.p_y_given_x = symbolic_softmax(self.y_out)
        self.y_pred = T.argmax(self.p_y_given_x, axis=-1)


class LSTM_layer(object):

    def __init__(self, x, n_input, n_hidden):
        print "Initialize LSTM layer..."
        # n_candidate = n_output
        # Init weights :
        init_norm = 0.01
        # Input weights :
        W_i_init = np.asarray(np.random.uniform(size=(n_input, n_hidden),
                                          low=-init_norm, high=init_norm),
                                          dtype=theano.config.floatX)

        self.W_i = theano.shared(value=W_i_init,name='W_i')

        # Forget weights  :

        W_f_init = np.asarray(np.random.uniform(size=(n_input, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.W_f = theano.shared(value=W_f_init,name='W_f')

        # Candidate weights :

        W_c_init = np.asarray(np.random.uniform(size=(n_input, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.W_c = theano.shared(value=W_c_init,name='W_c')

        # Output weights
        W_o_init = np.asarray(np.random.uniform(size=(n_input, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.W_o = theano.shared(value=W_o_init,name='W_o')


        # Input state weights :
        U_i_init = np.asarray(np.random.uniform(size=(n_hidden, n_hidden),
                                          low=-init_norm, high=init_norm),
                                          dtype=theano.config.floatX)

        self.U_i = theano.shared(value=U_i_init,name='U_i')

        # Forget state weights  :

        U_f_init = np.asarray(np.random.uniform(size=(n_hidden, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.U_f = theano.shared(value=U_f_init,name='U_f')
        
        
        # Candidates state weights :
        U_c_init = np.asarray(np.random.uniform(size=(n_hidden, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.U_c = theano.shared(value=U_c_init,name='U_c')
        
                
        # Output state weights :
        U_o_init = np.asarray(np.random.uniform(size=(n_hidden, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.U_o = theano.shared(value=U_o_init,name='U_o')

        # Output candidate weights
        V_o_init = np.asarray(np.random.uniform(size=(n_hidden, n_hidden),
                                  low=-init_norm, high=init_norm),
                                  dtype=theano.config.floatX)
        self.V_o = theano.shared(value=V_o_init,name='V_o')

        # Init hidden state vector :

        h_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.h = theano.shared(value=h_init, name='h')

        # Init biases :

        # forget biases:

        bf_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.bf = theano.shared(value=bf_init, name='bf')

        # input biases :
        bi_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.bi= theano.shared(value=bi_init, name='bi')


        # candidate biases :
        bc_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.bc= theano.shared(value=bc_init, name='bc')
        
        
        # candidate biases :
        bo_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.bo= theano.shared(value=bo_init, name='bo')
        
        ho_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.h0 = theano.shared(value=ho_init,name='h0')

        co_init = np.zeros((n_hidden), dtype=theano.config.floatX)
        self.c0 = theano.shared(value=co_init,name='c0')

        self.c = T.matrix()
        
        # xt
        
        # x = [x1,...,xt,...,xn]
        self.x = x


        [self.h,self.c], updates = theano.scan(fn=self.step,sequences=self.x,outputs_info=[self.h0,self.c0])
        #self.h = theano.tensor.extra_ops.squeeze(self.h)
        # Formulas :

        # Wi, Wf, Wc, Wo, Ui, Uf, Uc, Uo, Vo

        # it = sigma(Wi*xt + Ui*ht-1 + bi)
        # Ctest = tanh(Wc*xt + Uc*ht-1 + bc)
        # ft = sigma( Wf*xt + Uf*ht-1 + bf )
        # Ct = it* Ctest +ft*Ct-1
        # ot = sigma(Woxt + Uo*ht-1 + VoCt +bo)
        # ht = ot * tanh(Ct)

        print "Initialization of LSTM layer done!"

    def step(self,xt,ht_pre,ct_pre):
        it = T.nnet.sigmoid(T.dot(xt,self.W_i)+T.dot(ht_pre,self.U_i)+self.bi)
        ct_est = T.tanh(T.dot(xt,self.W_c)+T.dot(ht_pre,self.U_c)+self.bc)
        ft = T.nnet.sigmoid(T.dot(xt,self.W_f)+T.dot(ht_pre,self.U_f)+self.bf)
        ct = it*ct_est+ft*ct_pre
        ot = T.nnet.sigmoid(T.dot(xt,self.W_o)+T.dot(ht_pre,self.U_o)+T.dot(ct,self.V_o)+self.bo)
        ht = ot*T.tanh(ct)

        return ht,ct


# Class quite useful for batch the training trough files
class SequenceDataset:
  '''Slices, shuffles and manages a small dataset for the HF optimizer.'''

  def __init__(self, data, batch_size, number_batches, minimum_size=10):
    '''SequenceDataset __init__
  data : list of lists of numpy arrays
    Your dataset will be provided as a list (one list for each graph input) of
    variable-length tensors that will be used as mini-batches. Typically, each
    tensor is a sequence or a set of examples.
  batch_size : int or None
    If an int, the mini-batches will be further split in chunks of length
    `batch_size`. This is useful for slicing subsequences or provide the full
    dataset in a single tensor to be split here. All tensors in `data` must
    then have the same leading dimension.
  number_batches : int
    Number of mini-batches over which you iterate to compute a gradient or
    Gauss-Newton matrix product.
  minimum_size : int
    Reject all mini-batches that end up smaller than this length.'''

    self.current_batch = 0
    self.number_batches = number_batches
    self.items = []

    for i_sequence in xrange(len(data[0])):
      if batch_size is None:
        self.items.append([data[i][i_sequence] for i in xrange(len(data))])
      else:
        for i_step in xrange(0, len(data[0][i_sequence]) - minimum_size + 1, batch_size):
          self.items.append([data[i][i_sequence][i_step:i_step + batch_size] for i in xrange(len(data))])
    self.shuffle()

  def shuffle(self):
    np.random.shuffle(self.items)

  def iterate(self, update=True):
    # iterate over the dataset returning number_batches [x,y] in an iterable
    for b in xrange(self.number_batches):
      yield self.items[(self.current_batch + b) % len(self.items)]
    # update the current batch ( starting point )
    if update: self.update()

  def update(self):
    if self.current_batch + self.number_batches >= len(self.items):
      self.shuffle()
      self.current_batch = 0
    else:
      self.current_batch += self.number_batches


if __name__ == '__main__':

    trX, trY = process()

    n_in = trX[0].shape[1]
    n_hidden = 40
    n_layers = 1
    n_updates = 100000
    n_classes = 7
    # Store the raw classes anyway
    #labels = trY
    # Compute probabilistic labelling :
    #trY = [int_to_label(i,n_classes) for i in trY]


    # Try a toy example :

    gradient_dataset = SequenceDataset([trX, trY], batch_size=None,
                                       number_batches=len(trX))

    cg_dataset = SequenceDataset([trX, trY], batch_size=None,
                                       number_batches=len(trX) )
    model = LSTM(n_in,n_layers,n_hidden,n_classes)

    # Use hessian free optimization :
    # opt = hf_optimizer(p=model.params,inputs=[model.x,model.y],s=model.softmax_layer.y_out,h=model.lstm_layer.h,
    #                    model=model,costs=[model.cost,model.cost],
    #                    teX=trX,teY=trY)
    #
    # opt.train(gradient_dataset,cg_dataset,num_updates=n_updates)
    # pause()
    # Train using gradient descent
    for i in range(n_updates):
        model.train(gradient_dataset)





