/*
 Navicat Premium Dump SQL

 Source Server         : 工控机192.168.1.136
 Source Server Type    : MySQL
 Source Server Version : 80045 (8.0.45)
 Source Host           : 192.168.1.136:3306
 Source Schema         : iot_db

 Target Server Type    : MySQL
 Target Server Version : 80045 (8.0.45)
 File Encoding         : 65001

 Date: 28/04/2026 12:16:46
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for production_process
-- ----------------------------
DROP TABLE IF EXISTS `production_process`;
CREATE TABLE `production_process`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `startup_process` int NULL DEFAULT NULL COMMENT '启动流程',
  `end_the_process` int NULL DEFAULT NULL COMMENT '结束流程',
  `process_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '工艺名称',
  `process_description` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '工艺描述',
  `enable_or_not` tinyint(1) NULL DEFAULT NULL COMMENT '是否启用:1启用，0禁用',
  `if_delete` tinyint(1) NULL DEFAULT NULL COMMENT '是否删除：1删除，0不删除',
  `if_run` tinyint(1) NULL DEFAULT NULL COMMENT '是否运行：1运行中，0未启动',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
