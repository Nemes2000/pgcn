from __future__ import division
from __future__ import print_function
from operator import itemgetter
import time

import tensorflow as tf
import numpy as np
import networkx as nx
import scipy.sparse as sp
from sklearn import metrics
import matplotlib.pyplot as plt
import h5py
import pickle
import os

from decagon.deep.optimizer import DecagonOptimizer
from decagon.deep.model import DecagonModel
from decagon.deep.minibatch import EdgeMinibatchIterator
from decagon.utility import rank_metrics, preprocessing

# os.environ["CUDA_DEVICE_ORDER"] = 'PCI_BUS_ID'
# os.environ["CUDA_VISIBLE_DEVICES"] = '1'
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
# config = tf.ConfigProto()
# config.gpu_options.allow_growth = True

np.random.seed(0)

def tsne_visualization(matrix):
    from sklearn.manifold import TSNE
    import matplotlib.pyplot as plt
    plt.figure(dpi=300)
    tsne = TSNE(n_components=2, verbose=1, perplexity=40, random_state=0,
            n_iter=1000)
    tsne_results = tsne.fit_transform(matrix)
    plt.scatter(tsne_results[:, 0], tsne_results[:, 1])
    plt.xlabel('x')
    plt.ylabel('y')
    plt.show()

def draw_graph(adj_matrix):
    G = nx.from_scipy_sparse_matrix(adj_matrix)
    pos = nx.spring_layout(G, iterations=100)
    d = dict(nx.degree(G))
    nx.draw(G, pos, node_color=range(3215), nodelist=d.keys(), 
        node_size=[v*20+20 for v in d.values()], cmap=plt.cm.Dark2)
    plt.show()

def get_accuracy_scores(edges_pos, edges_neg, edge_type, name=None):
    feed_dict.update({placeholders['dropout']: 0})
    feed_dict.update({placeholders['batch_edge_type_idx']: minibatch.edge_type2idx[edge_type]})
    feed_dict.update({placeholders['batch_row_edge_type']: edge_type[0]})
    feed_dict.update({placeholders['batch_col_edge_type']: edge_type[1]})
    rec = sess.run(opt.predictions, feed_dict=feed_dict)

    def sigmoid(x):
        return 1. / (1 + np.exp(-x))

    preds = []
    actual = []
    predicted = []
    edge_ind = 0
    for u, v in edges_pos[edge_type[:2]][edge_type[2]]:
        score = sigmoid(rec[u, v])
        preds.append(score)

        assert adj_mats_orig[edge_type[:2]][edge_type[2]][u,v] == 1, 'Problem 1'

        actual.append(edge_ind)
        predicted.append((score, edge_ind))
        edge_ind += 1

    preds_neg = []
    for u, v in edges_neg[edge_type[:2]][edge_type[2]]:
        score = sigmoid(rec[u, v])
        preds_neg.append(score)
        assert adj_mats_orig[edge_type[:2]][edge_type[2]][u,v] == 0, 'Problem 0'

        predicted.append((score, edge_ind))
        edge_ind += 1

    preds_all = np.hstack([preds, preds_neg])
    preds_all = np.nan_to_num(preds_all)
    labels_all = np.hstack([np.ones(len(preds)), np.zeros(len(preds_neg))])
    predicted = list(zip(*sorted(predicted, reverse=True, key=itemgetter(0))))[1]

    roc_sc = metrics.roc_auc_score(labels_all, preds_all)
    aupr_sc = metrics.average_precision_score(labels_all, preds_all)
    apk_sc = rank_metrics.apk(actual, predicted, k=200)
    #bedroc_sc = bedroc_score(labels_all, preds_all)
    if name!=None:
        with open(name, 'wb') as f:
            pickle.dump([labels_all, preds_all], f)
    return roc_sc, aupr_sc, apk_sc#, bedroc_sc


def construct_placeholders(edge_types):
    tf.compat.v1.disable_eager_execution()
    placeholders = {
        'batch': tf.compat.v1.placeholder(tf.int64, name='batch'),
        'batch_edge_type_idx': tf.compat.v1.placeholder(tf.int64, shape=(), name='batch_edge_type_idx'),
        'batch_row_edge_type': tf.compat.v1.placeholder(tf.int64, shape=(), name='batch_row_edge_type'),
        'batch_col_edge_type': tf.compat.v1.placeholder(tf.int64, shape=(), name='batch_col_edge_type'),
        'degrees': tf.compat.v1.placeholder(tf.int64),
        'dropout': tf.compat.v1.placeholder_with_default(0., shape=()),
    }
    placeholders.update({
        'adj_mats_%d,%d,%d' % (i, j, k): tf.compat.v1.sparse_placeholder(tf.float32)
        for i, j in edge_types for k in range(edge_types[i,j])})
    placeholders.update({
        'feat_%d' % i: tf.compat.v1.sparse_placeholder(tf.float32)
        for i, _ in edge_types})
    return placeholders

#csak az adott értéknél biztosabb éleket válogatja össze
def network_edge_threshold(network_adj, threshold):
    edge_tmp, edge_value, shape_tmp = preprocessing.sparse_to_tuple(network_adj)
    preserved_edge_index = np.where(edge_value>threshold)[0]
    preserved_network = sp.csr_matrix(
        (edge_value[preserved_edge_index], 
        (edge_tmp[preserved_edge_index,0], edge_tmp[preserved_edge_index, 1])),
        shape=shape_tmp)
    return preserved_network


def get_prediction(edge_type):
    feed_dict.update({placeholders['dropout']: 0})
    feed_dict.update({placeholders['batch_edge_type_idx']: minibatch.edge_type2idx[edge_type]})
    feed_dict.update({placeholders['batch_row_edge_type']: edge_type[0]})
    feed_dict.update({placeholders['batch_col_edge_type']: edge_type[1]})
    rec = sess.run(opt.predictions, feed_dict=feed_dict)

    return 1. / (1 + np.exp(-rec))


#-------------------------------
# mátrixok összerakása
#-------------------------------

gene_phenes_path = './data_prioritization/genes_phenes.mat'
f = h5py.File(gene_phenes_path, 'r')
gene_network_adj = sp.csc_matrix((np.array(f['GeneGene_Hs']['data']),
    np.array(f['GeneGene_Hs']['ir']), np.array(f['GeneGene_Hs']['jc'])),
    shape=(12331,12331))
gene_network_adj = gene_network_adj.tocsr()
disease_network_adj = sp.csc_matrix((np.array(f['PhenotypeSimilarities']['data']),
    np.array(f['PhenotypeSimilarities']['ir']), np.array(f['PhenotypeSimilarities']['jc'])),
    shape=(3215, 3215))
disease_network_adj = disease_network_adj.tocsr()
disease_network_adj = network_edge_threshold(disease_network_adj, 0.2)

dg_ref = f['GenePhene'][0][0]
gene_disease_adj = sp.csc_matrix((np.array(f[dg_ref]['data']),
    np.array(f[dg_ref]['ir']), np.array(f[dg_ref]['jc'])),
    shape=(12331, 3215))
gene_disease_adj = gene_disease_adj.tocsr()

novel_associations_adj = sp.csc_matrix((np.array(f['NovelAssociations']['data']),
    np.array(f['NovelAssociations']['ir']), np.array(f['NovelAssociations']['jc'])),
    shape=(12331,3215))


#---------------------------------------
# gén tulajdonságok feldolgozása
#---------------------------------------


gene_feature_path = './data_prioritization/GeneFeatures.mat'
f_gene_feature = h5py.File(gene_feature_path,'r')
gene_feature_exp = np.array(f_gene_feature['GeneFeatures'])
gene_feature_exp = np.transpose(gene_feature_exp)
gene_network_exp = sp.csc_matrix(gene_feature_exp)

row_list = [3215, 1137, 744, 2503, 1143, 324, 1188, 4662, 1243]
gene_feature_list_other_spe = list()
for i in range(1,9):
    dg_ref = f['GenePhene'][i][0]
    disease_gene_adj_tmp = sp.csc_matrix((np.array(f[dg_ref]['data']),
        np.array(f[dg_ref]['ir']), np.array(f[dg_ref]['jc'])),
        shape=(12331, row_list[i]))
    gene_feature_list_other_spe.append(disease_gene_adj_tmp)


#---------------------------------------
# gén, betegség tulajdonságok feldolgozása
#---------------------------------------


disease_tfidf_path = './data_prioritization/clinicalfeatures_tfidf.mat'
f_disease_tfidf = h5py.File(disease_tfidf_path)
disease_tfidf = np.array(f_disease_tfidf['F'])
disease_tfidf = np.transpose(disease_tfidf)
disease_tfidf = sp.csc_matrix(disease_tfidf)

dis_dis_adj_list= list()
dis_dis_adj_list.append(disease_network_adj)

val_test_size = 0.1
n_genes = 12331
n_dis = 3215
n_dis_rel_types = len(dis_dis_adj_list) # == 1
gene_adj = gene_network_adj
gene_degrees = np.array(gene_adj.sum(axis=0)).squeeze()

gene_dis_adj = gene_disease_adj
dis_gene_adj = gene_dis_adj.transpose(copy=True)

dis_degrees_list = [np.array(dis_adj.sum(axis=0)).squeeze() for dis_adj in dis_dis_adj_list]

adj_mats_orig = {
    (0, 0): [gene_adj, gene_adj.transpose(copy=True)],
    (0, 1): [gene_dis_adj],
    (1, 0): [dis_gene_adj],
    (1, 1): dis_dis_adj_list + [x.transpose(copy=True) for x in dis_dis_adj_list],
}
degrees = {
    0: [gene_degrees, gene_degrees],
    1: dis_degrees_list + dis_degrees_list,
}

gene_feat = sp.hstack(gene_feature_list_other_spe+[gene_feature_exp])
gene_nonzero_feat, gene_num_feat = gene_feat.shape
gene_feat = preprocessing.sparse_to_tuple(gene_feat.tocoo())

dis_feat = disease_tfidf
dis_nonzero_feat, dis_num_feat = dis_feat.shape
dis_feat = preprocessing.sparse_to_tuple(dis_feat.tocoo())

num_feat = {
    0: gene_num_feat,
    1: dis_num_feat,
}
nonzero_feat = {
    0: gene_nonzero_feat,
    1: dis_nonzero_feat,
}
feat = {
    0: gene_feat,
    1: dis_feat,
}



#---------------------------------------
# élek
#---------------------------------------


edge_type2dim = {k: [adj.shape for adj in adjs] for k, adjs in adj_mats_orig.items()}
# edge_type2decoder = {
#     (0, 0): 'bilinear',
#     (0, 1): 'bilinear',
#     (1, 0): 'bilinear',
#     (1, 1): 'bilinear',
# }

edge_type2decoder = {
    (0, 0): 'innerproduct',
    (0, 1): 'innerproduct',
    (1, 0): 'innerproduct',
    (1, 1): 'innerproduct',
}

edge_types = {k: len(v) for k, v in adj_mats_orig.items()}
num_edge_types = sum(edge_types.values())
print("Edge types:", "%d" % num_edge_types) # fix 6


#------------------------------------------------

if __name__ == '__main__':

    flags = {
        'neg_sample_size': 1,
        'learning_rate': 0.001,
        'hidden1': 64,
        'hidden2': 32,
        'weight_decay': 0.001,
        'dropout': 0.1,
        'max_margin': 0.1,
        'batch_size': 512,
        'bias': True,
        'epoch': 50,
        "print_progress": 150
    }

    print("Defining placeholders")
    placeholders = construct_placeholders(edge_types)

    print("Create minibatch iterator")
    minibatch = EdgeMinibatchIterator(
        adj_mats=adj_mats_orig,
        feat=feat,
        edge_types=edge_types,
        batch_size=flags['batch_size'],
        val_test_size=val_test_size
    )

    print("Create model")
    model = DecagonModel(
        placeholders=placeholders,
        num_feat=num_feat,
        nonzero_feat=nonzero_feat,
        edge_types=edge_types,
        decoders=edge_type2decoder,
    )

    print("Create optimizer")
    with tf.name_scope('optimizer'):
        opt = DecagonOptimizer(
            embeddings=model.embeddings,
            latent_inters=model.latent_inters,
            latent_varies=model.latent_varies,
            degrees=degrees,
            edge_types=edge_types,
            edge_type2dim=edge_type2dim,
            placeholders=placeholders,
            batch_size=flags['batch_size'],
            margin=flags['max_margin']
        )

    print("Initialize session")
    sess = tf.compat.v1.Session()
    sess.run(tf.compat.v1.global_variables_initializer())
    feed_dict = {}
    # saver = tf.compat.v1.train.Saver()
    # saver.restore(sess,'./model/model.ckpt')
    # feed_dict = minibatch.next_minibatch_feed_dict(placeholders=placeholders)
    # feed_dict = minibatch.update_feed_dict(
    #     feed_dict=feed_dict,
    #     dropout=flags['dropout'],
    #     placeholders=placeholders)

    print("Train model")
    for epoch in range(flags["epoch"]):

        minibatch.shuffle()
        itr = 0
        while not minibatch.end():
            # Construct feed dictionary
            feed_dict = minibatch.next_minibatch_feed_dict(placeholders=placeholders)
            feed_dict = minibatch.update_feed_dict(
                feed_dict=feed_dict,
                dropout=flags["dropout"],
                placeholders=placeholders)

            t = time.time()

            # Training step: run single weight update
            outs = sess.run([opt.opt_op, opt.cost, opt.batch_edge_type_idx], feed_dict=feed_dict)
            train_cost = outs[1]
            batch_edge_type = outs[2]

            if itr % flags["print_progress"] == 0:
                val_auc, val_auprc, val_apk = get_accuracy_scores(
                    minibatch.val_edges, minibatch.val_edges_false,
                    minibatch.idx2edge_type[minibatch.current_edge_type_idx])

                print("Epoch:", "%04d" % (epoch + 1), "Iter:", "%04d" % (itr + 1), "Outs:", outs,
                    "val_roc=", "{:.5f}".format(val_auc), "val_auprc=", "{:.5f}".format(val_auprc),
                    "val_apk=", "{:.5f}".format(val_apk), "time=", "{:.5f}".format(time.time() - t))

            itr += 1

    print("Optimization finished!")

    roc_score, auprc_score, apk_score = get_accuracy_scores(
        minibatch.test_edges, minibatch.test_edges_false, minibatch.idx2edge_type[3])
    print("Edge type=", "[%02d, %02d, %02d]" % minibatch.idx2edge_type[3])
    print("Edge type:", "%04d" % 3, "Test AUROC score", "{:.5f}".format(roc_score))
    print("Edge type:", "%04d" % 3, "Test AUPRC score", "{:.5f}".format(auprc_score))
    print("Edge type:", "%04d" % 3, "Test AP@k score", "{:.5f}".format(apk_score))
    #print("Edge type:", "%04d" % 3, "Test BEDROC score", "{:.5f}".format(bedroc))
    print()

    prediction = get_prediction(minibatch.idx2edge_type[3])

    print('Saving result...')
    np.save('./result/prediction.npy', prediction)