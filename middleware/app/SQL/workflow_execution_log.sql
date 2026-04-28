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

 Date: 27/04/2026 17:10:33
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for workflow_execution_log
-- ----------------------------
DROP TABLE IF EXISTS `workflow_execution_log`;
CREATE TABLE `workflow_execution_log`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `workflow_id` int NOT NULL COMMENT '工作流id',
  `execution_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '工作流执行状态',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '错误信息',
  `frequency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '执行频率',
  `communication_params` json NULL COMMENT '通讯参数(JSON格式)：ip,端口,寄存器地址等',
  `workflow_detail` json NULL COMMENT '工作流详情(JSON格式)',
  `is_deleted` tinyint(1) NULL DEFAULT 0 COMMENT '逻辑删除标志：0-未删除，1-已删除',
  `deleted_at` datetime NULL DEFAULT NULL COMMENT '删除时间',
  `execution_start_time` datetime NOT NULL COMMENT '执行开始时间',
  `execution_end_time` datetime NULL DEFAULT NULL COMMENT '执行结束时间',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_workflow_status`(`workflow_id` ASC, `execution_status` ASC) USING BTREE,
  INDEX `idx_execution_time`(`execution_start_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '工作流执行日志表' ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
