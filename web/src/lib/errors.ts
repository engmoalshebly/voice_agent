import { ConnectionError, MediaDeviceFailure } from 'livekit-client';
import { TokenError } from './api';

export interface FriendlyError {
  title: string;
  detail: string;
  retryable: boolean;
}

/** Map any failure to a sentence a caller understands; never leak raw errors. */
export function describeError(error: unknown): FriendlyError {
  if (error instanceof TokenError) {
    switch (error.code) {
      case 'rate_limited':
        return { title: 'محاولات كثيرة', detail: 'بدأت عدة مكالمات خلال وقت قصير. انتظر دقيقة ثم حاول مجدداً.', retryable: true };
      case 'origin_forbidden':
        return { title: 'مصدر غير مسموح', detail: 'افتح المساعد من رابطه الرسمي.', retryable: false };
      case 'channel_unavailable':
        return { title: 'القناة غير متاحة', detail: 'هذه القناة غير مفعّلة حالياً. تواصل مع صاحب الموقع.', retryable: false };
      case 'not_configured':
        return { title: 'الخدمة غير جاهزة', detail: 'خدمة الصوت قيد الإعداد حالياً. حاول لاحقاً.', retryable: true };
      case 'network':
        return { title: 'لا يوجد اتصال', detail: 'تحقق من اتصالك بالإنترنت ثم حاول مجدداً.', retryable: true };
      default:
        return { title: 'تعذر بدء المكالمة', detail: 'حدث خطأ في الخادم. حاول مجدداً بعد قليل.', retryable: true };
    }
  }
  const failure = MediaDeviceFailure.getFailure(error);
  if (failure === MediaDeviceFailure.PermissionDenied) {
    return { title: 'الميكروفون محظور', detail: 'اسمح للمتصفح باستخدام الميكروفون من شريط العنوان، ثم حاول مجدداً.', retryable: true };
  }
  if (failure === MediaDeviceFailure.NotFound) {
    return { title: 'لا يوجد ميكروفون', detail: 'وصّل ميكروفوناً أو سماعة ثم حاول مجدداً.', retryable: true };
  }
  if (failure === MediaDeviceFailure.DeviceInUse) {
    return { title: 'الميكروفون مشغول', detail: 'أغلق التطبيقات الأخرى التي تستخدم الميكروفون ثم حاول مجدداً.', retryable: true };
  }
  if (error instanceof ConnectionError) {
    return { title: 'تعذر فتح مسار الصوت', detail: 'قد تمنع الشبكة اتصالات الصوت. جرّب شبكة أخرى أو حاول لاحقاً.', retryable: true };
  }
  return { title: 'حدث خطأ غير متوقع', detail: 'حاول مجدداً. إن تكرر الأمر فأعد تحميل الصفحة.', retryable: true };
}
