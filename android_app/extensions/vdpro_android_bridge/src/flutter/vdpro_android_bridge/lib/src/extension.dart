import 'package:flet/flet.dart';

import 'service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    if (control.type == 'AndroidMediaService') {
      return AndroidMediaServiceControl(control: control);
    }
    return null;
  }
}
