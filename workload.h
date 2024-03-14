#ifndef _WORKLOAD_H_
#define _WORKLOAD_H_

#include "utils.h"

typedef struct _Workload {
  void *key_buf;
  void *val_buf;
  uint32_t *key_size_list;
  uint32_t *val_size_list;
  uint8_t *op_list;
  uint32_t num_ops;
} Workload;

static void load_ycsb_single(char *wl_name, int num_load_ops,
                             uint32_t server_id, uint32_t all_client_num,
                             __OUT Workload *wl) {
  char wl_fname[128];
  sprintf(wl_fname, "../workloads/ycsb/%s", wl_name);
  FILE *f = fopen(wl_fname, "r");
  assert(f != NULL);
  printd(L_INFO, "Client %d loading %s", server_id, wl_name);

  std::vector<std::string> wl_list;
  char buf[2048];
  uint32_t cnt = 0;
  while (fgets(buf, 2048, f) == buf) {
    if (buf[0] == '\n')
      continue;
    if ((cnt % all_client_num) + 1 == server_id)
      wl_list.emplace_back(buf);
    cnt++;
  }

  if (num_load_ops == -1)
    wl->num_ops = wl_list.size();
  else
    wl->num_ops = num_load_ops;
  wl->key_buf = malloc(128 * wl->num_ops);
  wl->val_buf = malloc(120 * wl->num_ops);
  wl->key_size_list = (uint32_t *)malloc(sizeof(uint32_t) * wl->num_ops);
  wl->val_size_list = (uint32_t *)malloc(sizeof(uint32_t) * wl->num_ops);
  wl->op_list = (uint8_t *)malloc(sizeof(uint8_t) * wl->num_ops);
  memset(wl->key_buf, 0, 128 * wl->num_ops);
  memset(wl->val_buf, 0, 120 * wl->num_ops);

  printf("Client %d loading %ld ops\n", server_id, wl_list.size());
  char ops_buf[64];
  char key_buf[64];
  for (int i = 0; i < wl->num_ops; i++) {
    sscanf(wl_list[i].c_str(), "%s %s", ops_buf, key_buf);
    memcpy((void *)((uint64_t)wl->key_buf + i * 128), key_buf, 128);
    memcpy((void *)((uint64_t)wl->val_buf + i * 120), &i, sizeof(int));
    wl->key_size_list[i] = strlen(key_buf);
    wl->val_size_list[i] = sizeof(int);
    if (strcmp("READ", ops_buf) == 0) {
      wl->op_list[i] = GET;
    } else {
      wl->op_list[i] = SET;
    }
  }
}

static void load_workload_ycsb(char *wl_name, int num_load_ops,
                               uint32_t server_id, uint32_t all_client_num,
                               __OUT Workload *load_wl,
                               __OUT Workload *trans_wl) {
  char fname_buf[256];
  sprintf(fname_buf, "%s.load", wl_name);
  // server_id starts with 1
  load_ycsb_single(fname_buf, num_load_ops, server_id, all_client_num, load_wl);

  sprintf(fname_buf, "%s.trans", wl_name);
  load_ycsb_single(fname_buf, num_load_ops, server_id, all_client_num,
                   trans_wl);
}

static void load_workload_ycsb_load(int num_load_ops, uint32_t server_id,
                                    uint32_t all_client_num,
                                    __OUT Workload *wl) {
  load_ycsb_single("ycsb.load", num_load_ops, server_id, all_client_num, wl);
}

static void load_workload_ycsb_trans(char *wl_name, int num_load_ops,
                                     uint32_t server_id,
                                     uint32_t all_client_num,
                                     __OUT Workload *wl) {
  char fname_buf[256];
  sprintf(fname_buf, "%s.load", wl_name);
  load_ycsb_single(fname_buf, num_load_ops, server_id, all_client_num, wl);
}

static inline void
get_workload_kv(Workload *wl, uint32_t idx, __OUT uint64_t *key_addr,
                __OUT uint64_t *val_addr, __OUT uint32_t *key_size,
                __OUT uint32_t *val_size, __OUT uint8_t *op) {
  idx = idx % wl->num_ops;
  *key_addr = ((uint64_t)wl->key_buf + idx * 128);
  *val_addr = ((uint64_t)wl->val_buf + idx * 120);
  *key_size = wl->key_size_list[idx];
  *val_size = wl->val_size_list[idx];
  *op = wl->op_list[idx];
}

#endif