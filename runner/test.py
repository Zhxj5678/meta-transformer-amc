import os
import torch
import torch.utils.data as DATA
import torch.nn.functional as F
import tqdm
from runner.utils import get_config, model_selection
from data.dataset import AMCTestDataset, FewShotDataset, FewShotDatasetForOnce
from models.proto import load_protonet_conv, load_protonet_robustcnn, load_protonet_vit
from plot.conf_matrix import plot_confusion_matrix


class Tester:
    def __init__(self, config, model_path=None, save_path=None, per_snr=False):
        self.config = get_config(config)
        self.use_cuda = self.config['cuda']
        self.device_ids = self.config['gpu_ids']
        self.batch_size = self.config['batch_size']
        self.per_snr = per_snr

        if model_path is None:
            self.model_path = self.config['load_test_path']
        else:
            self.model_path = model_path

        self.net = model_selection(self.config["model_name"])

        if self.use_cuda:
            self.net.to(self.device_ids[0])

    def test(self):
        print("Cuda: ", torch.cuda.is_available())
        print("Device id: ", self.device_ids[0])

        model_name = self.config['model_name']
        robust = False
        if model_name == 'robustcnn':
            robust = True

        self.net.load_state_dict(torch.load(self.model_path))

        if not self.per_snr:
            test_data = AMCTestDataset(self.config["test_dataset_path"], robust=robust, snr_range=self.config["snr_range"])
            test_dataloader = DATA.DataLoader(test_data, batch_size=self.batch_size, shuffle=True)

            correct = 0
            total = 0

            self.net.eval()
            with torch.no_grad():
                for i, sample in enumerate(tqdm.tqdm(test_dataloader)):
                    if self.use_cuda:
                        x = sample["data"].to(self.device_ids[0])
                        labels = sample["label"].to(self.device_ids[0])
                        # snr = sample["snr"].to(self.device_ids[0])
                    else:
                        x = sample["data"]
                        labels = sample["label"]
                    outputs = self.net(x)
                    outputs = F.softmax(outputs, dim=1)

                    _, pred = torch.max(outputs, 1)

                    total += labels.size(0)
                    correct += (pred == labels).sum().item()

            print(f'Accuracy: : {correct / total} %')

            f = open(os.path.join(os.path.dirname(self.model_path), "acc.txt"), "w")
            f.write(f"Total Accuracy: {correct / total}\n")
            f.close()

        else:
            snr_range = range(self.config["snr_range"][0], self.config["snr_range"][1] + 1, 2)

            f = open(os.path.join(os.path.dirname(self.model_path), "acc.txt"), "w")

            for snr in snr_range:
                correct = 0
                total = 0
                test_data = AMCTestDataset(self.config["test_dataset_path"], robust=robust, snr_range=(snr, snr))
                test_dataloader = DATA.DataLoader(test_data, batch_size=self.batch_size, shuffle=True)

                self.net.eval()
                with torch.no_grad():
                    for i, sample in enumerate(tqdm.tqdm(test_dataloader)):
                        if self.use_cuda:
                            x = sample["data"].to(self.device_ids[0])
                            labels = sample["label"].to(self.device_ids[0])
                            # snr = sample["snr"].to(self.device_ids[0])
                        else:
                            x = sample["data"]
                            labels = sample["label"]
                        outputs = self.net(x)
                        outputs = F.softmax(outputs, dim=1)

                        _, pred = torch.max(outputs, 1)

                        total += labels.size(0)
                        correct += (pred == labels).sum().item()

                print(f'Accuracy: : {correct / total}')

                f.write(f"SNR {snr} Accuracy: {correct / total}\n")
            f.close()

    def fs_test(self, now):
        print("Cuda: ", torch.cuda.is_available())
        print("Device id: ", self.device_ids[0])

        model_name = self.config['fs_model']
        robust = False
        if model_name != 'vit':
            robust = True

        n_way = len(self.config['test_class_indices'])

        test_data = FewShotDataset(self.config["dataset_path"],
                                   num_support=self.config["num_support"],
                                   num_query=self.config["num_query"],
                                   robust=robust,
                                   mode='test',
                                   snr_range=self.config["snr_range"])
        test_dataloader = DATA.DataLoader(test_data, batch_size=1, shuffle=True)

        if model_name == 'protonet':
            model = load_protonet_conv(
                x_dim=(1, 512, 256),
                hid_dim=32,
                z_dim=24,
            )
        elif model_name == 'robustcnn':
            model = load_protonet_robustcnn()
        elif model_name == 'vit':
            model = load_protonet_vit()

        model.load_state_dict(torch.load(self.model_path))

        conf_mat = torch.zeros(n_way, n_way)
        running_loss = 0.0
        running_acc = 0.0

        model.eval()
        with torch.no_grad():
            for episode, sample in enumerate(tqdm.tqdm(test_dataloader)):
                output = model.proto_test(sample)

                a = output['y_hat'].cpu().int()

                for cls in range(n_way):
                    conf_mat[cls, :] = conf_mat[cls, :] + torch.bincount(a[cls, :], minlength=n_way)

                running_acc += output['acc']

        avg_acc = running_acc / (episode+1)
        plot_confusion_matrix(conf_mat,
                              classes=[self.config['total_class'][cls] for cls in self.config['test_class_indices']])
        print('Test results -- Acc: {:.4f}'.format(avg_acc))

    def fs_test_once(self, now):
        print("Cuda: ", torch.cuda.is_available())
        print("Device id: ", self.device_ids[0])

        n_way = len(self.config['test_class_indices'])

        model_name = self.config['fs_model']
        robust = False
        if model_name != 'vit':
            robust = True

        test_data = FewShotDataset(self.config["dataset_path"],
                                   num_support=self.config["num_support"],
                                   num_query=self.config["num_query"],
                                   robust=robust, mode='test',
                                   snr_range=self.config["snr_range"])
        test_dataloader = DATA.DataLoader(test_data, batch_size=1, shuffle=True)

        if model_name == 'protonet':
            model = load_protonet_conv(
                x_dim=(1, 512, 256),
                hid_dim=32,
                z_dim=11,
            )
        elif model_name == 'robustcnn':
            model = load_protonet_robustcnn()
        elif model_name == 'vit':
            model = load_protonet_vit()

        model.load_state_dict(torch.load(self.model_path))

        conf_mat = torch.zeros(n_way, n_way)
        running_loss = 0.0
        running_acc = 0.0
        z_proto = None

        model.eval()
        with torch.no_grad():
            for episode, sample in enumerate(tqdm.tqdm(test_dataloader)):
                if episode == 0:
                    # Create target domain Prototype Network with support set(target domain)
                    z_proto = model.create_protoNet(sample)

                output = model.proto_test_once(sample, z_proto)
                a = output['y_hat'].cpu().int()
                for cls in range(n_way):
                    conf_mat[cls, :] = conf_mat[cls, :] + torch.bincount(a[cls, :], minlength=n_way)
                running_acc += output['acc']

        avg_acc = running_acc / (episode+1)
        plot_confusion_matrix(conf_mat,
                              classes=[self.config['total_class'][cls] for cls in
                                       self.config['test_class_indices']])
        print('Test results -- Acc: {:.4f}'.format(avg_acc))


