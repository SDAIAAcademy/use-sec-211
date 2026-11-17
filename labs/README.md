# الذكاء الاصطناعي في الزراعة والمياه والبيئة: المختبرات

ستة عشر مختبرًا لمقرر أكاديمية سدايا **USE-SEC-211**: ثمانية من 25 دقيقة (1.3، 1.4، 1.6، 1.7، 2.2، 2.3، 2.6، 2.8)
وثمانية من 20 دقيقة، فمجموعها ست ساعات كما في خطة المقرر. المختبرات صفحات إرشادية بالعربية: الهدف، والملفات، وخطوات
بدقائقها وصيغ جاهزة لجدول البيانات، وأسئلة تحقق، وتمرين إضافي ✱، وملاحظات للمدرب. لا كود يكتبه المشارك.

كل المختبرات في جهة واحدة: **هيئة السُّقيا للمياه والزراعة**، جهة افتراضية.

## ما هو حقيقي وما هو توضيحي

- **قياسات من بيانات عامة:** انعكاس صور Sentinel-2 (المستوى 2A) فوق نافذة من المحاور الدائرية، وخريطة ESA WorldCover
  2021، والتبخر نتح المرجعي والمطر من ERA5، والتنبؤات اليومية كما صدرت في 2024.
- **اصطناعي:** الهيئة وأشخاصها، وتصريحات القطع ورموز المزارعين ونتائج الزيارات، ومزرعة الهدّار وجدولها ومجسها، وعدادات
  المناطق وسجل الإصلاحات، وحالات الاستخدام الاثنتا عشرة.
- **توضيحي:** المكان والقطع وأرقامها. لا يذكر أي ملف موقع النافذة ولا إحداثيات قطعة، والصورة في الشرائح مقصوصة ومقلوبة،
  فلا يُنسب تصريح أو نتيجة زيارة إلى حقل حقيقي ولا إلى صاحبه.

## ما يحتاجه المشارك

- جدول بيانات يقرأ CSV بترميز UTF-8 ويرسم خطًّا بيانيًّا: LibreOffice Calc أو Microsoft Excel أو Google Sheets.
- مساعد ذكاء اصطناعي عام اختياري، بالدرجة التي تعلنها كل صفحة: لا شيء في 1.6 و1.7، ومعلّم في مختبرات الصور والري
  والتسرب، وكامل في 2.8. لا يحتاج أي مختبر نموذجًا ولا مفتاحًا ولا خدمة مدفوعة، ولا يُنزَّل شيء على الجهاز.

## نقطة البداية والحل

لا يعتمد مختبر على مختبر قبله في اليوم نفسه: حين يكمل مختبر عمل سابقه، يبدأ من ملف جاهز في `files/start/`.
حل كل مختبر في أمرين: قسمه في `solutions/check.py` الذي يعيد حساب كل رقم من ملفات المشارك، ومفتاح المدرب في آخر صفحة
المختبر. ولمختبرات الكتابة حل مكتوب أيضًا.

| المختبر | الصفحة | الدقائق | يبدأ من | الحل المكتوب |
|---|---|---|---|---|
| 1.1 | `D1_1_monitoring_sources.html` | 20 | `monitoring_questions.csv`، `sources_card.txt`، `prework_sheet.csv` | `solutions/D1_1_monitoring_sources.md` |
| 1.2 | `D1_2_clear_scenes.html` | 20 | `imagery/scenes.csv`، `imagery/plot_sizes.csv` | مفتاح الصفحة |
| 1.3 | `D1_3_ndvi_series.html` | 25 | `imagery/plots_reflectance.csv`، `imagery/crop_calendar.txt` | مفتاح الصفحة |
| 1.4 | `D1_4_plot_flags.html` | 25 | `start/plots_ndvi.csv`، `declarations.csv`، `crop_rules.txt` | مفتاح الصفحة |
| 1.5 | `D1_5_field_checks.html` | 20 | `start/flags.csv`، `field_team.txt` | `solutions/D1_5_field_checks.md` |
| 1.6 | `D1_6_confusion_matrix.html` | 25 | `landcover/points.csv` | مفتاح الصفحة |
| 1.7 | `D1_7_accuracy_uses.html` | 25 | `start/confusion_matrix.csv`، `landcover/proposed_uses.csv` | مفتاح الصفحة |
| 1.8 | `D1_8_field_campaign.html` | 20 | `start/accuracy_table.csv`، `landcover/campaign_costs.txt` | مفتاح الصفحة |
| 2.1 | `D2_1_forecast_skill.html` | 20 | `weather/et0_forecasts_2024.csv` | `solutions/D2_1_forecast_skill.md` |
| 2.2 | `D2_2_fixed_schedule.html` | 25 | `farm/season_2024.csv`، `farm/farm_profile.txt` | مفتاح الصفحة |
| 2.3 | `D2_3_schedule_comparison.html` | 25 | `start/season_fixed.csv` | مفتاح الصفحة |
| 2.4 | `D2_4_uncertainty.html` | 20 | `start/scenarios.csv` | `solutions/D2_4_uncertainty.md` |
| 2.5 | `D2_5_night_flow.html` | 20 | `meters/zone_hourly.csv`، `meters/zone_events.txt` | مفتاح الصفحة |
| 2.6 | `D2_6_leak_alerts.html` | 25 | `meters/alerts_by_threshold.csv`، `meters/crew_capacity.txt` | مفتاح الصفحة |
| 2.7 | `D2_7_data_rights.html` | 20 | `map/use_cases.csv`، `map/scoring_guide.txt` | `solutions/D2_7_data_rights.md` |
| 2.8 | `D2_8_opportunity_map.html` | 25 | `start/register.csv`، `map/scoring_guide.txt` | `solutions/D2_8_opportunity_map.md` |

## تشغيل الحلول

```bash
uv run labs/solutions/check.py            # كل المختبرات
uv run labs/solutions/check.py 1.4 2.3    # بعضها
```

ملف واحد بمكتبة بايثون القياسية فقط، يحتاج [uv](https://docs.astral.sh/uv/). يطبع لكل مختبر ما أعاد حسابه و`PASS`،
ولا يكتب شيئًا على القرص ولا يتصل بأي نموذج أو خدمة. كل المختبرات حسابات على الملفات، فتُشغَّل حلولها كاملة؛ ومختبرات
الكتابة (1.1، 2.7، 2.8) تُفحص على مفاتيحها ودليل التقييم، أما نصوص المشاركين (طلبات التحقق والخطابات والرسائل والخريطة)
فيقرؤها المدرب.

## إعادة بناء الملفات

للمؤلف فقط، وتحتاج اتصالًا بالإنترنت: `_tools/fetch_public.py` يجلب البيانات العامة إلى مجلد خارج المقرر (حدود النافذة
تُمرَّر له ولا تُكتب في المستودع)، ثم `_tools/prepare_files.py` يكتب `files/` و`solutions/key.json` بالبذرة 211.
النصوص الاصطناعية في `_tools/case_texts.py`.

## ذكر المصادر

يحتوي على بيانات Copernicus Sentinel معدّلة (2021، 2023، 2024). ‏© ESA WorldCover project 2021، بيانات Copernicus
Sentinel (2021) معالجة من اتحاد ESA WorldCover، برخصة CC BY 4.0. بيانات الطقس من Open-Meteo.com برخصة CC BY 4.0،
وأُعدّت قيم ERA5 باستعمال معلومات خدمة Copernicus لتغير المناخ (2024).
