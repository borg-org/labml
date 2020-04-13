# Kaggle Competition https://www.kaggle.com/c/liverpool-ion-switching/overview
# download data from the above line provided

import numpy as np

import torch
import torch.optim as optim
import torch.nn as nn
import torch.utils.data

from sklearn.metrics import f1_score

from lab import logger, configs
from lab import training_loop
from lab.experiment.pytorch import Experiment
from lab.logger.util import pytorch as logger_util

from lab.util.data.pytorch import CsvDataset


class EncoderRNN(nn.Module):
    def __init__(self, batch_size, n_seq, embed_size=10, input_size=1, hidden_size=50, n_classes=1):
        super(EncoderRNN, self).__init__()

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.embed_size = embed_size
        self.n_classes = n_classes
        self.n_seq = n_seq
        self.batch_size = batch_size
        self.n_layers = 1
        self.n_directions = 1

        self.layer1 = nn.Linear(input_size, embed_size)
        self.gru = nn.GRU(embed_size, hidden_size, batch_first=True)
        self.out = nn.Linear(hidden_size, n_classes)

    def forward(self, x, hidden):
        layer1 = self.layer1(x).view(-1, self.n_seq, self.embed_size)

        output, hidden = self.gru(layer1, hidden)
        output = self.out(output).view(-1, self.n_classes)

        return output, hidden

    def init_hidden(self, device):
        return torch.zeros(self.n_layers * self.n_directions, self.batch_size, self.hidden_size, device=device)


class RNN:
    def __init__(self, c: 'Configs'):
        self.batch_size = c.batch_size
        self.epochs = c.epochs

        self.device = c.device

        self.encoder = c.encoder
        self.optimizer = c.optimizer
        self.loss = c.loss

        self.train_loader = c.train_loader
        self.test_loader = c.test_loader

        self.train_log_interval = c.train_log_interval
        self.loop = c.training_loop
        self.__is_log_parameters = c.is_log_parameters

    def _train(self):
        for i, (input_tensor, target_tensor) in logger.enum("Train", self.train_loader):
            encoder_hidden = self.encoder.init_hidden(self.device).double().to(self.device)

            input_tensor = input_tensor.to(self.device).unsqueeze(1)
            target_tensor = target_tensor.to(self.device).double()

            self.optimizer.zero_grad()
            encoder_output, encoder_hidden = self.encoder(input_tensor, encoder_hidden)

            train_loss = self.loss(encoder_output, target_tensor)

            train_loss.backward()
            self.optimizer.step()

            logger.store(loss=train_loss.item())
            logger.add_global_step()
            logger.write()

    def _test(self):
        self.encoder.eval()

        with torch.no_grad():
            macro_f1s = []
            test_losses = []
            for input_tensor, target_tensor in logger.iterate("Test", self.test_loader):
                encoder_hidden = self.encoder.init_hidden(self.device).double().to(self.device)

                input_tensor = input_tensor.to(self.device).unsqueeze(1)
                target_tensor = target_tensor.to(self.device).double()

                encoder_output, encoder_hidden = self.encoder(input_tensor, encoder_hidden)

                test_loss = self.loss(encoder_output, target_tensor)

                macro_f1 = f1_score(y_true=target_tensor.cpu().detach().numpy().ravel(),
                                    y_pred=encoder_output.cpu().detach().to(torch.int32).numpy().ravel(),
                                    average='macro')

                test_losses.append(test_loss)
                macro_f1s.append(macro_f1)

            logger.store(test_loss=np.mean(test_losses))
            logger.store(accuracy=np.mean(macro_f1s))
            logger.write()

    def __log_model_params(self):
        if not self.__is_log_parameters:
            return

        logger_util.store_model_indicators(self.encoder)

    def __call__(self):
        logger_util.add_model_indicators(self.encoder)

        for _ in self.loop:
            self._train()
            self._test()
            self.__log_model_params()


class LoaderConfigs(configs.Configs):
    train_loader: torch.utils.data.DataLoader
    test_loader: torch.utils.data.DataLoader


class Configs(training_loop.TrainingLoopConfigs, LoaderConfigs):
    epochs: int = 100

    loop_step = 'loop_step'
    loop_count = 'loop_count'

    is_save_models = True
    batch_size: int = 10
    test_batch_size: int = 10

    n_seq = 500

    use_cuda: float = True
    cuda_device: int = 0
    seed: int = 5
    train_log_interval: int = 10

    is_log_parameters: bool = True

    device: any

    encoder: nn.Module

    optimizer: optim
    lr: float = 0.0002
    beta: tuple = (0.5, 0.999)
    loss = nn.MSELoss()

    set_seed = 'set_seed'

    main: RNN


@Configs.calc(Configs.encoder)
def set_encoder(c: Configs):
    return EncoderRNN(c.batch_size, c.n_seq).to(c.device).double()


@Configs.calc(Configs.optimizer)
def optimizer(c: Configs):
    return optim.Adam(c.encoder.parameters(), lr=c.lr, betas=c.beta)


@Configs.calc(Configs.set_seed)
def set_seed(c: Configs):
    torch.manual_seed(c.seed)


@Configs.calc(Configs.loop_count)
def loop_count(c: Configs):
    return c.epochs * len(c.train_loader)


@Configs.calc(Configs.loop_step)
def loop_step(c: Configs):
    return len(c.train_loader)


@Configs.calc(Configs.device)
def device(*, use_cuda, cuda_device):
    from lab.util.pytorch import get_device

    return get_device(use_cuda, cuda_device)


def _custom_dataset(is_train):
    return CsvDataset(file_path=f'{logger.get_data_path()}/liverpool-ion-switching/train.csv',
                      train=is_train,
                      test_fraction=0.1,
                      x_cols=['signal'],
                      y_cols=['open_channels'])


def _data_loader(is_train, batch_size):
    return torch.utils.data.DataLoader(_custom_dataset(is_train), batch_size=batch_size,
                                       drop_last=True, num_workers=15)


@Configs.calc([Configs.train_loader, Configs.test_loader])
def data_loaders(c: Configs):
    train = _data_loader(True, c.batch_size * c.n_seq)
    test = _data_loader(False, c.test_batch_size * c.n_seq)

    return train, test


def main():
    conf = Configs()
    experiment = Experiment(writers={'sqlite', 'tensorboard'})
    experiment.calc_configs(conf,
                            {},
                            run_order=['set_seed', 'main'])
    experiment.start()
    conf.main()


if __name__ == '__main__':
    main()