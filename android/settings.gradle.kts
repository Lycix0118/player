// 儿童视频播放器 · 安卓平板客户端
//
// ⚠️ 本机磁盘约束：C 盘只剩 ~950MB，D 盘剩 ~56GB。
// 因此源码留在仓库（随 git 走），但**所有构建产物与临时目录都重定向到 D 盘**。
// 见下方 gradle.beforeProject —— 每个模块的 buildDir 被改写到 D:/gradle-build/kidstv/<模块名>。
val externalBuildRoot = File("D:/gradle-build/kidstv")

gradle.beforeProject {
    val moduleName = if (path == ":") "root" else path.removePrefix(":").replace(':', '-')
    layout.buildDirectory.set(File(externalBuildRoot, moduleName))
}

pluginManagement {
    repositories {
        // 国内网络：阿里云镜像放最前（实测 6.98MB/s，官方 maven 仅 467KB/s）
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
        google {
            content {
                includeGroupByRegex("androidx.*")
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        google {
            content {
                includeGroupByRegex("androidx.*")
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
            }
        }
        mavenCentral()
    }
}

plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "KidsTv"
include(":app")
