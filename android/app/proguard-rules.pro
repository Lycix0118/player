# 默认不开混淆（release 也如此）；如需开启，补上 kotlinx.serialization 与 OkHttp 的 keep 规则。
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.lcx.kidstv.core.model.** { *; }
