import java.lang.reflect.InvocationTargetException;

/** Read-only Android OEM lock queries; no settings changes or Binder transaction guesses. */
public final class A31OemState {
    public static void main(String[] args) throws Exception {
        Class<?> manager = Class.forName("android.os.ServiceManager");
        Object binder = manager.getMethod("getService", String.class).invoke(null, "oem_lock");
        if (binder == null) {
            System.out.println("oem_lock=UNAVAILABLE");
            return;
        }
        Class<?> stub = Class.forName("android.service.oemlock.IOemLockService$Stub");
        Object service = stub.getMethod("asInterface", Class.forName("android.os.IBinder"))
                .invoke(null, binder);
        Class<?> api = Class.forName("android.service.oemlock.IOemLockService");
        String[] reads = {
            "getLockName", "isOemUnlockAllowedByCarrier", "isOemUnlockAllowedByUser",
            "isOemUnlockAllowed", "isDeviceOemUnlocked"
        };
        for (String name : reads) {
            try {
                System.out.println(name + "=" + api.getMethod(name).invoke(service));
            } catch (InvocationTargetException error) {
                Throwable cause = error.getCause();
                System.out.println(name + "=UNAVAILABLE (" + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage() + ")");
            } catch (ReflectiveOperationException error) {
                System.out.println(name + "=UNAVAILABLE (" + error + ")");
            }
        }
    }
}
