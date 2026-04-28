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

 Date: 27/04/2026 17:09:33
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for device_instance
-- ----------------------------
DROP TABLE IF EXISTS `device_instance`;
CREATE TABLE `device_instance`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `device_model_id` int NULL DEFAULT NULL COMMENT '设备型号id',
  `device_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备编号',
  `device_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备名称',
  `device_category` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备类别',
  `production_line` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '所属产线',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '所在位置',
  `device_status` tinyint NULL DEFAULT 0 COMMENT '设备状态：0-离线，1-在线，2-运行中，3-故障',
  `device_data` json NULL COMMENT '设备数据(JSON格式)：运行时长、最大容量等',
  `communication_protocol` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备通讯协议',
  `is_deleted` tinyint(1) NULL DEFAULT 0 COMMENT '逻辑删除标志：0-未删除，1-已删除',
  `deleted_at` datetime NULL DEFAULT NULL COMMENT '删除时间',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `recent_maintenance_time` datetime NULL DEFAULT NULL COMMENT '最近维护时间',
  `commissioning_time` datetime NULL DEFAULT NULL COMMENT '投运时间',
  `device_image` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备图片',
  `enable_or_not` tinyint NULL DEFAULT NULL COMMENT '是否启用:1启用，2禁用',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `device_code`(`device_code` ASC) USING BTREE,
  INDEX `idx_device_model`(`device_model_id` ASC) USING BTREE,
  INDEX `idx_status`(`device_status` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 10 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '设备实例表' ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
